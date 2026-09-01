from __future__ import annotations

import logging

from .backup_retention import prune_syncapp_backups
from .config import Settings
from .drift import detect_live_drift
from .git_repo import GitRepository
from .mirror import save_manifest
from .policy import collect_allowed_files, is_allowed_relative
from .staging import StagingResult
from .supervisor import SupervisorClient
from .transaction import (
    FileTransaction,
    TransactionError,
    build_apply_plan,
    execute_verified_transaction,
    recover_active_transaction,
)


LOGGER = logging.getLogger(__name__)


def _managed_paths_at_commit(repository: GitRepository, commit: str) -> set[str]:
    return {
        entry.path
        for entry in repository.tree_entries(commit)
        if entry.object_type == "blob" and is_allowed_relative(entry.path)
    }


def recover_interrupted_apply(settings: Settings, repository: GitRepository) -> bool:
    active = FileTransaction.load_active(
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

    # A crash can happen after Core was verified and adopt_remote() advanced the
    # isolated Git HEAD, but before manifest/journal cleanup finished. Once Git has
    # adopted the verified commit, automatically rolling back live files would move
    # the live tree behind the repository baseline. Prove both Git HEAD and the live
    # managed files still match before finalizing bookkeeping.
    if active.state == "verified":
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

    desired_paths = collect_allowed_files(settings.staging_dir)
    plan = build_apply_plan(
        settings.staging_dir,
        baseline_paths,
        staged.commit,
        live_dir=settings.source_dir,
    )
    if not plan.affected_paths:
        repository.fetch()
        repository.adopt_remote(staged.commit)
        save_manifest(settings.manifest_path, desired_paths)
        return ()

    supervisor = SupervisorClient()
    transaction = FileTransaction.prepare(
        settings.transaction_dir,
        settings.source_dir,
        settings.staging_dir,
        plan,
    )

    try:
        result = execute_verified_transaction(
            transaction,
            supervisor,
            health_timeout_seconds=settings.verify_timeout_seconds,
        )
        repository.fetch()
        repository.adopt_remote(result.commit)
        save_manifest(settings.manifest_path, desired_paths)
        transaction.complete()
    except Exception as exc:
        active = FileTransaction.load_active(
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

    LOGGER.info(
        "Applied and verified remote commit %s (%d affected paths, backup %s)",
        result.commit,
        len(result.affected_paths),
        result.backup_slug,
    )

    # Retention is post-commit hygiene only. It must never turn a verified apply
    # into a rollback or remove the backup created for the just-completed apply.
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
