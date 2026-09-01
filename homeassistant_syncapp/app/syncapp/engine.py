from __future__ import annotations

import logging

from .apply import apply_staged_remote, recover_interrupted_apply
from .config import Settings
from .git_repo import GitRepository
from .mirror import load_manifest, mirror_local_configuration, save_manifest
from .policy import is_allowed_relative
from .staging import (
    StagingValidationError,
    stage_remote_configuration,
    validate_configuration_directory,
)
from .supervisor import SupervisorClient, SupervisorError
from .transaction import TransactionError


LOGGER = logging.getLogger(__name__)


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

        if relationship == "local_ahead":
            if self.settings.dry_run:
                LOGGER.warning(
                    "Local branch is ahead of GitHub, but dry-run is enabled; push skipped"
                )
                return
            LOGGER.warning("Local branch is ahead of GitHub; retrying previous push")
            self.repository.push()
            LOGGER.info("Previously committed local changes were pushed successfully")
            return

        previous_managed = load_manifest(self.settings.manifest_path)
        current_managed = mirror_local_configuration(
            self.settings.source_dir,
            self.settings.repository_dir,
            previous_managed,
        )
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
            save_manifest(self.settings.manifest_path, current_managed)
            LOGGER.info("No relevant local configuration changes detected")
            return

        LOGGER.info("Detected %d relevant local change(s): %s", len(changed), ", ".join(changed))

        try:
            validated = validate_configuration_directory(self.settings.repository_dir)
            SupervisorClient().check_core_configuration()
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
        self.repository.push()
        save_manifest(self.settings.manifest_path, current_managed)
        LOGGER.info("Pushed local Home Assistant configuration commit %s", commit)
