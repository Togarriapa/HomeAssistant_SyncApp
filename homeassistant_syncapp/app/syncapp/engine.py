from __future__ import annotations

import hashlib
import logging

from .apply import (
    apply_staged_initial_remote,
    apply_staged_remote,
    recover_interrupted_apply,
)
from .config import Settings
from .git_repo import GitError, GitRepository, GitTreeEntry
from .mirror import ManifestError, load_manifest, mirror_local_configuration, save_manifest
from .policy import is_allowed_relative
from .staging import (
    StagingValidationError,
    stage_remote_configuration,
    validate_configuration_directory,
)
from .supervisor import SupervisorClient, SupervisorError
from .transaction import TransactionError


LOGGER = logging.getLogger(__name__)
_ALLOWED_INDEX_MODES = {"100644", "100755"}


def _entries_sha256_manifest(
    repository: GitRepository,
    entries: list[GitTreeEntry],
    *,
    label: str,
) -> tuple[tuple[str, str], ...]:
    try:
        manifest: list[tuple[str, str]] = []
        for entry in entries:
            if (
                entry.object_type != "blob"
                or entry.mode not in _ALLOWED_INDEX_MODES
                or not is_allowed_relative(entry.path)
            ):
                raise StagingValidationError(
                    f"{label} contains unsupported or blocked entry: {entry.path}"
                )
            manifest.append(
                (entry.path, hashlib.sha256(repository.read_blob(entry.object_id)).hexdigest())
            )
        return tuple(sorted(manifest))
    except GitError as exc:
        raise StagingValidationError(f"could not bind {label}: {exc}") from exc


def _index_sha256_manifest(repository: GitRepository) -> tuple[tuple[str, str], ...]:
    try:
        entries = repository.index_tree_entries()
    except GitError as exc:
        raise StagingValidationError(f"could not bind staged Git index: {exc}") from exc
    return _entries_sha256_manifest(repository, entries, label="staged Git index")


def _commit_sha256_manifest(
    repository: GitRepository,
    commit: str,
) -> tuple[tuple[str, str], ...]:
    try:
        entries = repository.tree_entries(commit)
    except GitError as exc:
        raise StagingValidationError(f"could not inspect unpushed commit: {exc}") from exc
    return _entries_sha256_manifest(repository, entries, label="unpushed Git commit")


class SyncEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = GitRepository(
            path=settings.repository_dir,
            remote_url=settings.repository_url,
            branch=settings.branch,
            token=settings.github_token,
            user_name=settings.git_user_name,
            user_email=settings.git_user_email,
        )

    def _retry_unpushed_commit(self, relationship: str) -> None:
        if self.settings.dry_run:
            LOGGER.warning(
                "Managed branch has an unpushed commit, but dry-run is enabled; push skipped"
            )
            return

        try:
            count = self.repository.unpushed_commit_count()
            if count != 1:
                raise StagingValidationError(
                    f"refusing retry because managed branch has {count} unpushed commits; expected exactly one SyncApp commit"
                )
            head = self.repository.head()
            if head is None:
                raise StagingValidationError("managed branch has no HEAD for unpushed retry")

            committed = _commit_sha256_manifest(self.repository, head)
            live_before = validate_configuration_directory(self.settings.source_dir)
            if live_before.file_sha256 != committed:
                raise StagingValidationError(
                    "unpushed commit no longer matches live configuration before semantic validation"
                )

            SupervisorClient().check_core_configuration()

            live_after = validate_configuration_directory(self.settings.source_dir)
            if live_after.file_sha256 != committed:
                raise StagingValidationError(
                    "live configuration changed during unpushed-commit semantic validation"
                )
        except (GitError, StagingValidationError, SupervisorError) as exc:
            LOGGER.error(
                "Refusing automatic push retry for %s state: %s",
                relationship,
                exc,
            )
            return

        LOGGER.warning(
            "Managed branch is %s; revalidated its single unpushed commit against live Home Assistant configuration",
            relationship,
        )
        self.repository.push(head)
        try:
            save_manifest(
                self.settings.manifest_path,
                {path for path, _digest in committed},
            )
        except ManifestError as exc:
            LOGGER.error(
                "Unpushed commit was sent successfully, but managed-path manifest persistence failed: %s",
                exc,
            )
            return
        LOGGER.info("Previously committed local changes were revalidated and pushed successfully")

    def run_once(self) -> None:
        # A crash during a previous apply is resolved before any new Git activity.
        # Do not immediately retry the same remote commit in the recovery cycle.
        if recover_interrupted_apply(self.settings, self.repository):
            return

        self.repository.ensure()
        self.repository.fetch()
        relationship = self.repository.relationship()

        if relationship == "diverged":
            LOGGER.error(
                "Git state is diverged on branch %s; refusing both push and remote apply",
                self.settings.branch,
            )
            return

        if relationship in {"local_ahead", "local_only"}:
            self._retry_unpushed_commit(relationship)
            return

        # A missing manifest means SyncApp has not yet established a managed baseline.
        # A populated remote requires an explicit authority choice. Remote authority
        # is permitted only when the isolated clone exactly matches the fetched remote,
        # and it still uses the complete staged, backed-up, verified transaction path.
        if not self.settings.manifest_path.exists() and self.repository.remote_head() is not None:
            if relationship != "equal":
                LOGGER.error(
                    "Initial synchronization is ambiguous: remote branch %s is populated and Git relationship is %s; "
                    "refusing to choose an authority automatically",
                    self.settings.branch,
                    relationship,
                )
                return

            if self.settings.initial_remote_apply_enabled:
                try:
                    staged = stage_remote_configuration(
                        self.repository,
                        self.settings.staging_dir,
                    )
                except StagingValidationError as exc:
                    LOGGER.error("Rejected initial remote commit during staging validation: %s", exc)
                    return

                if self.settings.dry_run or not self.settings.remote_apply_enabled:
                    LOGGER.warning(
                        "Initial remote commit %s passed staging validation (%d files, %d bytes), "
                        "but bootstrap apply is disabled (dry_run=%s remote_apply_enabled=%s)",
                        staged.commit,
                        staged.file_count,
                        staged.total_bytes,
                        self.settings.dry_run,
                        self.settings.remote_apply_enabled,
                    )
                    return

                try:
                    affected = apply_staged_initial_remote(
                        self.repository,
                        self.settings,
                        staged,
                    )
                except TransactionError as exc:
                    LOGGER.error(
                        "Initial remote commit %s was not bootstrapped safely: %s",
                        staged.commit,
                        exc,
                    )
                    return

                LOGGER.info(
                    "Initial remote commit %s adopted successfully (%d affected paths)",
                    staged.commit,
                    len(affected),
                )
                return

            if not self.settings.initial_local_publish_enabled:
                LOGGER.error(
                    "Initial synchronization is blocked because remote branch %s is already populated. "
                    "Set exactly one initial authority option: initial_local_publish_enabled=true to publish the "
                    "validated live configuration, or initial_remote_apply_enabled=true to apply the validated "
                    "remote through the guarded transaction path",
                    self.settings.branch,
                )
                return
            LOGGER.warning(
                "Initial local publish is explicitly enabled; validated live Home Assistant configuration will be treated "
                "as authoritative for remote branch %s",
                self.settings.branch,
            )

        if relationship in {"remote_only", "remote_ahead"}:
            try:
                staged = stage_remote_configuration(
                    self.repository,
                    self.settings.staging_dir,
                )
            except StagingValidationError as exc:
                LOGGER.error("Rejected remote commit during staging validation: %s", exc)
                return

            if self.settings.dry_run or not self.settings.remote_apply_enabled:
                LOGGER.warning(
                    "Remote commit %s passed staging validation (%d files, %d bytes), "
                    "but live apply is disabled (dry_run=%s remote_apply_enabled=%s)",
                    staged.commit,
                    staged.file_count,
                    staged.total_bytes,
                    self.settings.dry_run,
                    self.settings.remote_apply_enabled,
                )
                return

            try:
                affected = apply_staged_remote(self.repository, self.settings, staged)
            except TransactionError as exc:
                LOGGER.error("Remote commit %s was not applied safely: %s", staged.commit, exc)
                return

            LOGGER.info(
                "Remote commit %s applied successfully (%d affected paths)",
                staged.commit,
                len(affected),
            )
            return

        try:
            previous_managed = load_manifest(self.settings.manifest_path)
            current_managed = mirror_local_configuration(
                self.settings.source_dir,
                self.settings.repository_dir,
                previous_managed,
            )
        except ManifestError as exc:
            LOGGER.error(
                "Managed-path manifest integrity check failed; refusing local synchronization: %s",
                exc,
            )
            return

        self.repository.add_all()
        changed = self.repository.staged_paths()

        unsafe_staged = [path for path in changed if not is_allowed_relative(path)]
        unsafe_tracked = [
            path for path in self.repository.tracked_paths() if not is_allowed_relative(path)
        ]
        unsafe = sorted(set(unsafe_staged) | set(unsafe_tracked))
        if unsafe:
            self.repository.discard_worktree_changes()
            LOGGER.error(
                "Refusing local synchronization because the Git baseline/candidate contains blocked paths: %s",
                ", ".join(unsafe),
            )
            return

        if not changed:
            try:
                save_manifest(self.settings.manifest_path, current_managed)
            except ManifestError as exc:
                LOGGER.error("Refusing to persist an unsafe managed-path manifest: %s", exc)
                return
            LOGGER.info("No relevant local configuration changes detected")
            return

        LOGGER.info("Detected %d relevant local change(s): %s", len(changed), ", ".join(changed))

        try:
            validated = validate_configuration_directory(self.settings.repository_dir)
            if _index_sha256_manifest(self.repository) != validated.file_sha256:
                raise StagingValidationError(
                    "staged Git index does not match the statically validated local candidate"
                )

            live_before = validate_configuration_directory(self.settings.source_dir)
            if live_before.file_sha256 != validated.file_sha256:
                raise StagingValidationError(
                    "live configuration no longer matches the mirrored candidate before semantic validation"
                )

            SupervisorClient().check_core_configuration()

            live_after = validate_configuration_directory(self.settings.source_dir)
            if live_after.file_sha256 != validated.file_sha256:
                raise StagingValidationError(
                    "live configuration changed during Home Assistant semantic validation"
                )
            if _index_sha256_manifest(self.repository) != validated.file_sha256:
                raise StagingValidationError(
                    "staged Git index changed during Home Assistant semantic validation"
                )
        except (StagingValidationError, SupervisorError) as exc:
            self.repository.discard_worktree_changes()
            LOGGER.error(
                "Rejected local configuration change before Git commit; live files were not modified: %s",
                exc,
            )
            return

        LOGGER.info(
            "Local candidate passed static and Home Assistant semantic validation (%d files, %d bytes)",
            validated.file_count,
            validated.total_bytes,
        )

        if self.settings.dry_run:
            self.repository.discard_worktree_changes()
            LOGGER.warning("Dry-run enabled; no commit or push performed")
            return

        commit = self.repository.commit("chore(homeassistant): sync local configuration")
        try:
            if _commit_sha256_manifest(self.repository, commit) != validated.file_sha256:
                raise StagingValidationError(
                    "created Git commit does not match the fully validated local candidate"
                )
        except StagingValidationError as exc:
            # HEAD now contains the suspect commit. Do not reset it automatically: the
            # single-commit recovery path will also refuse to push it unless it can be
            # independently revalidated against live Home Assistant configuration.
            LOGGER.error("Refusing to push newly created local commit: %s", exc)
            return

        self.repository.push(commit)
        try:
            save_manifest(self.settings.manifest_path, current_managed)
        except ManifestError as exc:
            LOGGER.error(
                "Git push succeeded, but managed-path manifest persistence failed integrity validation: %s",
                exc,
            )
            return
        LOGGER.info("Pushed local Home Assistant configuration commit %s", commit)
