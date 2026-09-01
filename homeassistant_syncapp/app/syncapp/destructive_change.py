from __future__ import annotations

from dataclasses import dataclass


class DestructiveChangeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeletionBudgetResult:
    deleted_paths: int
    baseline_paths: int
    deletion_percent: float


def enforce_remote_deletion_budget(
    delete_paths: tuple[str, ...],
    baseline_paths: set[str],
    *,
    max_deletions: int,
    max_deletion_percent: int,
) -> DeletionBudgetResult:
    """Reject unexpectedly destructive remote candidates before backup or live mutation."""
    deleted = len(delete_paths)
    baseline = len(baseline_paths)
    percent = (deleted * 100.0 / baseline) if baseline else 0.0

    if deleted > max_deletions:
        raise DestructiveChangeError(
            "remote candidate exceeds deletion safety budget: "
            f"{deleted} deletions > configured maximum {max_deletions}"
        )

    if baseline and percent > max_deletion_percent:
        raise DestructiveChangeError(
            "remote candidate exceeds deletion percentage safety budget: "
            f"{deleted}/{baseline} managed paths ({percent:.1f}%) > "
            f"configured maximum {max_deletion_percent}%"
        )

    return DeletionBudgetResult(
        deleted_paths=deleted,
        baseline_paths=baseline,
        deletion_percent=percent,
    )
