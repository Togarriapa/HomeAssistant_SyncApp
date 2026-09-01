from __future__ import annotations

import logging

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


def recover_interrupted_apply(settings: Settings) -> bool:
    active = FileTransaction.load_active(
        settings.transaction_dir,
        settings.source_dir,
        settings.staging_dir,
    )
    if active is None:
        return False

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
        baseline_paths = {
            entry.path
            for entry in repository.tree_entries(head)
            if entry.object_type == "blob" and is_allowed_relative(entry.path)
        }

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
    return result.affected_paths
