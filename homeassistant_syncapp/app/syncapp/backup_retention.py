from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

from .supervisor import SupervisorClient


LOGGER = logging.getLogger(__name__)
SYNCAPP_BACKUP_PREFIX = "SyncApp pre-apply "


@dataclass(frozen=True, slots=True)
class BackupCandidate:
    slug: str
    name: str
    created: datetime


def _parse_created(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def select_expired_syncapp_backups(
    backups: list[dict],
    *,
    retention_count: int,
    preserve_slugs: set[str] | None = None,
) -> tuple[str, ...]:
    """Return only safely identifiable, unprotected SyncApp backups beyond retention."""
    if retention_count < 0:
        raise ValueError("retention_count must not be negative")
    if retention_count == 0:
        return ()

    preserve = preserve_slugs or set()
    candidates: list[BackupCandidate] = []
    for item in backups:
        slug = item.get("slug")
        name = item.get("name")
        created = _parse_created(item.get("date"))
        protected = item.get("protected")

        # Fail closed on incomplete/ambiguous metadata. Retention is hygiene, not
        # permission to risk deleting a backup we cannot positively identify.
        if (
            not isinstance(slug, str)
            or not slug
            or not isinstance(name, str)
            or not name.startswith(SYNCAPP_BACKUP_PREFIX)
            or created is None
            or protected is not False
            or slug in preserve
        ):
            continue
        candidates.append(BackupCandidate(slug, name, created))

    candidates.sort(key=lambda item: item.created, reverse=True)
    return tuple(item.slug for item in candidates[retention_count:])


def prune_syncapp_backups(
    supervisor: SupervisorClient,
    *,
    retention_count: int,
    current_backup_slug: str | None = None,
) -> tuple[str, ...]:
    """Best-effort retention for backups created by successful SyncApp applies."""
    if retention_count == 0:
        return ()
    backups = supervisor.list_backups()
    preserve = {current_backup_slug} if current_backup_slug else set()
    expired = select_expired_syncapp_backups(
        backups,
        retention_count=retention_count,
        preserve_slugs=preserve,
    )
    deleted: list[str] = []
    for slug in expired:
        supervisor.delete_backup(slug)
        deleted.append(slug)
        LOGGER.info("Deleted expired unprotected SyncApp backup %s", slug)
    return tuple(deleted)
