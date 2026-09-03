from __future__ import annotations

import logging

from .backup_retention import prune_syncapp_backups
from .config import Settings
from .destructive_change import DestructiveChangeError, enforce_remote_deletion_budget
from .drift import detect_live_drift
from .git_repo import GitRepository
from .mirror import save_manifest
from .policy import collect_allowed_files, is_allowed_relative
from .recovery_loader import load_active_transaction
from .staging import StagingResult, StagingValidationError, assert_staging_integrity
from .supervisor import SupervisorClient
from .transaction import (
    FileTransaction,
    TransactionError,
    build_apply_plan,
    execute_verified_transaction,
    recover_active_transaction,
)
from .validated_plan import build_validated_apply_plan


LOGGER = logging.getLogger(__name__)


def _managed_paths_at_commit(repository: GitRepository, commit: str) -> set[str]:
    return {
        entry.path
        for entry in repository.tree_entries(commit)
        if entry.object_type == "blob" and is_allowed_relative(entry.path)
    }


def recover_interrupted_apply(settings: Settings, repository: GitRepository) -> bool:
    active = load_active_transaction(
        settings.transaction_dir,
        settings.source_dir,
        settings.staging_dir,
    )
    if active is None:
        return False

    if active.state == "verified_drift":
        raise TransactionError(
            "a previously verified/adopted transaction has subsequent live configuration drift; "
            "recovery evidence is preserved and automatic rollback is blocked"
        )

    if active.state in {"verified", "completed"}:
        try:
            adopted = repository.head() == active.plan.commit
        except Exception as exc:
            raise TransactionError(
                "verified transaction recovery cannot prove the Git baseline; "
                "leaving live files and recovery journal untouched"
            ) from exc

        if adopted:
            drift = detect_live_drift(repository, settings.source_dir)
            if not drift.clean:
                active.mark("verified_drift")
                raise TransactionError(
                    "verified remote commit was adopted, but live managed files changed before "
                    "transaction cleanup; refusing both finalize and rollback: "
                    + ", ".join(drift.changed)
                )
            try:
                save_manifest(
                    settings.manifest_path,
                    _managed_paths_at_commit(repository, active.plan.commit),
                )
                active.complete()
            except Exception as exc:
                raise TransactionError(
                    "verified transaction matched Git/live state, but bookkeeping could not be finalized; "
                    "recovery journal is preserved for retry"
                ) from exc
            LOGGER.warning(
                "Finalized previously verified remote commit %s after interrupted post-verification bookkeeping",
                active.plan.commit,
            )
            return True

        if active.state == "completed":
            raise TransactionError(
                "completed transaction no longer matches the adopted Git baseline; "
                "recovery evidence is preserved and automatic rollback is blocked"
            )

    LOGGER.error(
        "Found interrupted remote-apply transaction for %s in state %s; rolling back before sync",
        active.plan.commit,
        active.state,
    )
    supervisor = SupervisorClient()
    recover_active_transaction(
        active,
        supervisor,
        health_timeout_seconds=settings.verify_timeout_seconds,
    )
    LOGGER.warning("Interrupted remote-apply transaction was rolled back and verified")
    return True


def _execute_staged_apply(
    repository: GitRepository,
    settings: Settings,
    staged: StagingResult,
    baseline_paths: set[str],
    *,
    verify_noop: bool = False,
) -> tuple[str, ...]:
    try:
        assert_staging_integrity(settings.staging_dir, staged)
    except StagingValidationError as exc:
        raise TransactionError(
            f"validated staging tree changed before apply planning: {exc}"
        ) from exc

    if staged.integrity_bound:
        validated_hashes = staged.file_hashes
        desired_paths = set(validated_hashes)
        plan = build_validated_apply_plan(
            validated_hashes,
            baseline_paths,
            staged.commit,
            live_dir=settings.source_dir,
        )
    else:
        desired_paths = collect_allowed_files(settings.staging_dir)
        plan = build_apply_plan(
            settings.staging_dir,
            baseline_paths,
            staged.commit,
            live_dir=settings.source_dir,
        )

    try:
        deletion_result = enforce_remote_deletion_budget(
            plan.delete_paths,
            baseline_paths,
            max_deletions=settings.remote_max_deletions,
            max_deletion_percent=settings.remote_max_deletion_percent,
        )
    except DestructiveChangeError as exc:
        raise TransactionError(str(exc)) from exc

    if deletion_result.deleted_paths:
        LOGGER.warning(
            "Remote candidate %s deletes %d/%d managed paths (%.1f%%); within configured safety budget",
            staged.commit,
            deletion_result.deleted_paths,
            deletion_result.baseline_paths,
            deletion_result.deletion_percent,
        )

    if not plan.affected_paths:
        try:
            if verify_noop:
                SupervisorClient().check_core_configuration()
            repository.fetch()
            repository.adopt_remote(staged.commit)
            save_manifest(settings.manifest_path, desired_paths)
        except Exception as exc:
            raise TransactionError(f"remote no-op adoption failed safely: {exc}") from exc
        return ()

    supervisor = SupervisorClient()
    transaction = FileTransaction.prepare(
        settings.transaction_dir,
        settings.source_dir,
        settings.staging_dir,
        plan,
        staging_root_identity=staged.root_identity,
    )
    if staged.integrity_bound and transaction.plan.write_hashes != plan.write_hashes:
        transaction.discard()
        raise TransactionError(
            "staged source bytes changed after validated planning and before transaction preparation"
        )

    try:
        result = execute_verified_transaction(
            transaction,
            supervisor,
            health_timeout_seconds=settings.verify_timeout_seconds,
        )
    except Exception as exc:
        active = load_active_transaction(
            settings.transaction_dir,
            settings.source_dir,
            settings.staging_dir,
        )
        if active is not None:
            try:
                recover_active_transaction(
                    active,
                    supervisor,
                    health_timeout_seconds=settings.verify_timeout_seconds,
                )
            except Exception as recovery_error:
                raise TransactionError(
                    f"remote apply failed ({exc}); automatic recovery also failed ({recovery_error})"
                ) from recovery_error
        raise TransactionError(f"remote apply failed safely: {exc}") from exc

    try:
        repository.fetch()
        repository.adopt_remote(result.commit)
    except Exception as exc:
        active = load_active_transaction(
            settings.transaction_dir,
            settings.source_dir,
            settings.staging_dir,
        )
        if active is not None:
            try:
                recover_active_transaction(
                    active,
                    supervisor,
                    health_timeout_seconds=settings.verify_timeout_seconds,
                )
            except Exception as recovery_error:
                raise TransactionError(
                    f"verified remote apply could not adopt Git baseline ({exc}); "
                    f"automatic recovery also failed ({recovery_error})"
                ) from recovery_error
        raise TransactionError(
            f"verified remote apply could not adopt Git baseline and was rolled back safely: {exc}"
        ) from exc

    try:
        save_manifest(settings.manifest_path, desired_paths)
        transaction.complete()
    except Exception as exc:
        raise TransactionError(
            "verified remote commit was adopted, but post-verification bookkeeping failed; "
            "live files and verified recovery journal are preserved for safe finalization: "
            f"{exc}"
        ) from exc

    LOGGER.info(
        "Applied and verified remote commit %s (%d affected paths, backup %s)",
        result.commit,
        len(result.affected_paths),
        result.backup_slug,
    )

    if settings.backup_retention_count > 0:
        try:
            deleted = prune_syncapp_backups(
                supervisor,
                retention_count=settings.backup_retention_count,
                current_backup_slug=result.backup_slug,
            )
            if deleted:
                LOGGER.info("Pruned %d expired SyncApp backup(s)", len(deleted))
        except Exception:
            LOGGER.exception(
                "SyncApp backup retention failed after successful apply; synchronization remains accepted"
            )

    return result.affected_paths


def apply_staged_remote(
    repository: GitRepository,
    settings: Settings,
    staged: StagingResult,
) -> tuple[str, ...]:
    """Apply an already validated remote commit using a recoverable transaction."""
    drift = detect_live_drift(repository, settings.source_dir)
    if not drift.clean:
        raise TransactionError(
            "live Home Assistant configuration changed since local Git HEAD; "
            "refusing remote apply: " + ", ".join(drift.changed)
        )

    head = repository.head()
    baseline_paths: set[str] = set()
    if head is not None:
        baseline_paths = _managed_paths_at_commit(repository, head)

    return _execute_staged_apply(repository, settings, staged, baseline_paths)


def apply_staged_initial_remote(
    repository: GitRepository,
    settings: Settings,
    staged: StagingResult,
) -> tuple[str, ...]:
    """Adopt a populated remote as first authority through the full transaction path."""
    if settings.manifest_path.exists():
        raise TransactionError(
            "initial remote bootstrap is only valid before a managed-path baseline exists"
        )

    head = repository.head()
    if head != staged.commit:
        raise TransactionError(
            "initial remote bootstrap requires the isolated Git HEAD to equal the staged remote commit"
        )

    baseline_paths = collect_allowed_files(settings.source_dir)
    return _execute_staged_apply(
        repository,
        settings,
        staged,
        baseline_paths,
        verify_noop=True,
    )
