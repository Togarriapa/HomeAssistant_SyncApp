from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from syncapp.backup_archive import BackupArchiveError, verify_backup_archive
from syncapp.live_fs import LiveFilesystem, LiveFilesystemError
from syncapp.policy import collect_allowed_files
from syncapp.supervisor import SupervisorClient, SupervisorError


DEFAULT_DATA_ROOT = Path("/data")
DEFAULT_LIVE_ROOT = Path("/homeassistant")
DEFAULT_ARCHIVE_MAX_BYTES = 1024 * 1024 * 1024
DEFAULT_FREE_RESERVE_BYTES = 256 * 1024 * 1024


class CanaryStorageError(RuntimeError):
    pass


def _available_bytes(root: Path) -> int:
    if root.is_symlink():
        raise CanaryStorageError("canary data root must not be a symlink")
    if not root.is_dir():
        raise CanaryStorageError("canary data root is not an existing directory")
    try:
        info = os.statvfs(root)
    except OSError as exc:
        raise CanaryStorageError(f"cannot inspect canary data-root free space: {exc}") from exc
    return info.f_bavail * info.f_frsize


def _allowed_live_hashes(root: Path) -> dict[str, str]:
    if root.is_symlink():
        raise CanaryStorageError("live configuration root must not be a symlink")
    if not root.is_dir():
        raise CanaryStorageError("live configuration root is not an existing directory")
    paths = sorted(collect_allowed_files(root))
    if not paths:
        raise CanaryStorageError(
            "archive fidelity canary requires at least one policy-approved live file"
        )
    filesystem = LiveFilesystem(root)
    try:
        return {relative: filesystem.sha256(relative) for relative in paths}
    except LiveFilesystemError as exc:
        raise CanaryStorageError(
            f"cannot establish stable policy-approved live-file baseline: {exc}"
        ) from exc


def _elapsed(clock: Callable[[], float], started: float) -> float:
    elapsed = clock() - started
    if elapsed < 0:
        raise CanaryStorageError("monotonic canary clock moved backwards")
    return round(elapsed, 6)


def run_backup_storage_probe(
    client: SupervisorClient,
    *,
    data_root: Path = DEFAULT_DATA_ROOT,
    live_root: Path = DEFAULT_LIVE_ROOT,
    max_bytes: int = DEFAULT_ARCHIVE_MAX_BYTES,
    reserve_bytes: int = DEFAULT_FREE_RESERVE_BYTES,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    """Measure and byte-verify a fresh backup without risking data-root exhaustion.

    This is canary-only evidence. It intentionally does not change the production
    Backup -> Apply contract.
    """
    if max_bytes <= 0:
        raise CanaryStorageError("archive byte ceiling must be positive")
    if reserve_bytes <= 0:
        raise CanaryStorageError("free-space reserve must be positive")

    live_hashes_before = _allowed_live_hashes(live_root)

    required_free = max_bytes + reserve_bytes
    initial_available = _available_bytes(data_root)
    if initial_available < required_free:
        raise CanaryStorageError(
            "refusing backup archive probe because /data free space cannot cover the "
            f"configured download ceiling plus reserve: available={initial_available}, "
            f"required={required_free}"
        )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    backup_name = f"SyncApp storage canary {stamp}"

    started = clock()
    try:
        slug = client.create_homeassistant_backup(backup_name)
    except SupervisorError as exc:
        raise CanaryStorageError(f"Supervisor backup creation failed: {exc}") from exc
    create_seconds = _elapsed(clock, started)

    started = clock()
    try:
        backup_evidence = client.verify_homeassistant_backup(slug, backup_name)
    except SupervisorError as exc:
        raise CanaryStorageError(f"Supervisor backup verification failed: {exc}") from exc
    metadata_verify_seconds = _elapsed(clock, started)

    homeassistant_version = backup_evidence.get("homeassistant_version")
    if not isinstance(homeassistant_version, str) or not homeassistant_version.strip():
        raise CanaryStorageError(
            "verified backup evidence lost the Home Assistant version before archive proof"
        )

    before_download = _available_bytes(data_root)
    if before_download < required_free:
        raise CanaryStorageError(
            "refusing backup download because /data no longer has the configured "
            f"download ceiling plus reserve: available={before_download}, "
            f"required={required_free}"
        )

    archive_evidence: dict[str, object]
    downloaded_bytes: int
    after_download: int
    download_seconds: float
    archive_verify_seconds: float
    with TemporaryDirectory(prefix="syncapp-backup-storage-canary-", dir=data_root) as temporary:
        destination = Path(temporary) / "backup.tar"

        started = clock()
        try:
            downloaded_bytes = client.download_backup(
                slug,
                destination,
                max_bytes=max_bytes,
            )
        except SupervisorError as exc:
            raise CanaryStorageError(f"Supervisor backup download failed: {exc}") from exc
        download_seconds = _elapsed(clock, started)
        after_download = _available_bytes(data_root)
        if after_download < reserve_bytes:
            raise CanaryStorageError(
                "backup download reduced /data free space below the protected reserve; "
                "temporary archive will be removed before further validation"
            )

        started = clock()
        try:
            archive_evidence = verify_backup_archive(
                destination,
                expected_slug=slug,
                expected_name=backup_name,
                expected_homeassistant_version=homeassistant_version,
                expected_data_sha256=live_hashes_before,
            )
        except BackupArchiveError as exc:
            raise CanaryStorageError(f"downloaded backup archive canary failed: {exc}") from exc
        archive_verify_seconds = _elapsed(clock, started)

    live_hashes_after = _allowed_live_hashes(live_root)
    if live_hashes_after != live_hashes_before:
        raise CanaryStorageError(
            "policy-approved live configuration changed during backup fidelity measurement"
        )

    after_cleanup = _available_bytes(data_root)
    if after_cleanup < reserve_bytes:
        raise CanaryStorageError(
            "canary cleanup completed but /data remains below the protected free-space reserve"
        )

    return {
        "backup": backup_evidence,
        "archive": {
            "download_verified": True,
            "downloaded_bytes": downloaded_bytes,
            **archive_evidence,
            "live_file_set_stable": True,
            "temporary_download_removed": True,
        },
        "storage": {
            "data_root": str(data_root),
            "archive_max_bytes": max_bytes,
            "free_reserve_bytes": reserve_bytes,
            "required_free_bytes": required_free,
            "available_bytes_initial": initial_available,
            "available_bytes_before_download": before_download,
            "available_bytes_after_download": after_download,
            "available_bytes_after_cleanup": after_cleanup,
            "available_delta_during_download": after_download - before_download,
            "available_delta_after_cleanup": after_cleanup - before_download,
            "reserve_preserved_after_download": True,
            "reserve_preserved_after_cleanup": True,
        },
        "timings_seconds": {
            "backup_create": create_seconds,
            "backup_metadata_verify": metadata_verify_seconds,
            "backup_download": download_seconds,
            "archive_verify": archive_verify_seconds,
        },
    }
