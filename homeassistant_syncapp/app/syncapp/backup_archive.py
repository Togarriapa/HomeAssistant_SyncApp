from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import tarfile
from typing import IO


MAX_TAR_MEMBERS = 100_000
MAX_METADATA_BYTES = 1024 * 1024
_HOMEASSISTANT_ARCHIVES = {"homeassistant.tar", "homeassistant.tar.gz"}


class BackupArchiveError(RuntimeError):
    pass


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise BackupArchiveError("backup archive contains an unsafe member name")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise BackupArchiveError("backup archive contains an unsafe member path")
    return "/".join(part for part in path.parts if part not in {"", "."})


def _count_member(count: int) -> int:
    count += 1
    if count > MAX_TAR_MEMBERS:
        raise BackupArchiveError(
            f"backup archive exceeds the {MAX_TAR_MEMBERS} member safety limit"
        )
    return count


def _read_metadata_json(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    label: str,
) -> dict[str, object]:
    if not member.isfile() or not 0 < member.size <= MAX_METADATA_BYTES:
        raise BackupArchiveError(
            f"{label} is not a non-empty regular member within the metadata size limit"
        )
    stream: IO[bytes] | None = archive.extractfile(member)
    if stream is None:
        raise BackupArchiveError(f"cannot read {label}")
    with stream:
        raw = stream.read(MAX_METADATA_BYTES + 1)
    if len(raw) != member.size or len(raw) > MAX_METADATA_BYTES:
        raise BackupArchiveError(f"{label} metadata size is inconsistent or excessive")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupArchiveError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise BackupArchiveError(f"{label} JSON is not an object")
    return data


def verify_backup_archive(
    path: Path,
    *,
    expected_slug: str | None = None,
    expected_name: str | None = None,
    expected_homeassistant_version: str | None = None,
) -> dict[str, object]:
    """Verify a downloaded Supervisor backup without extracting configuration data."""
    outer_count = 0
    backup_json_members: list[tarfile.TarInfo] = []
    homeassistant_members: list[tarfile.TarInfo] = []

    try:
        with tarfile.open(path, mode="r:*") as outer:
            for member in outer:
                outer_count = _count_member(outer_count)
                name = _safe_member_name(member.name)
                if name == "backup.json":
                    backup_json_members.append(member)
                elif name in _HOMEASSISTANT_ARCHIVES:
                    if not member.isfile() or member.size <= 0:
                        raise BackupArchiveError(
                            "Home Assistant backup payload is not a non-empty regular member"
                        )
                    homeassistant_members.append(member)

            if len(backup_json_members) != 1:
                raise BackupArchiveError(
                    "downloaded backup does not contain exactly one backup.json"
                )
            if len(homeassistant_members) != 1:
                raise BackupArchiveError(
                    "downloaded backup does not contain exactly one Home Assistant archive"
                )

            backup_metadata = _read_metadata_json(
                outer, backup_json_members[0], "backup.json"
            )
            if expected_slug is not None and backup_metadata.get("slug") != expected_slug:
                raise BackupArchiveError(
                    "downloaded backup.json slug does not match the fresh canary backup"
                )
            if expected_name is not None and backup_metadata.get("name") != expected_name:
                raise BackupArchiveError(
                    "downloaded backup.json name does not match the fresh canary backup"
                )
            homeassistant_metadata = backup_metadata.get("homeassistant")
            if not isinstance(homeassistant_metadata, dict):
                raise BackupArchiveError(
                    "downloaded backup.json does not describe Home Assistant content"
                )
            if expected_homeassistant_version is not None:
                if homeassistant_metadata.get("version") != expected_homeassistant_version:
                    raise BackupArchiveError(
                        "downloaded backup.json Home Assistant version does not match API evidence"
                    )

            inner_stream = outer.extractfile(homeassistant_members[0])
            if inner_stream is None:
                raise BackupArchiveError("cannot read the Home Assistant backup archive member")

            inner_count = 0
            homeassistant_json_members: list[tarfile.TarInfo] = []
            data_file_count = 0
            try:
                with inner_stream, tarfile.open(fileobj=inner_stream, mode="r:*") as inner:
                    for member in inner:
                        inner_count = _count_member(inner_count)
                        name = _safe_member_name(member.name)
                        if name == "homeassistant.json":
                            homeassistant_json_members.append(member)
                        elif name.startswith("data/") and member.isfile():
                            data_file_count += 1
                    if len(homeassistant_json_members) != 1:
                        raise BackupArchiveError(
                            "Home Assistant component archive does not contain exactly one homeassistant.json"
                        )
                    _read_metadata_json(
                        inner,
                        homeassistant_json_members[0],
                        "homeassistant.json",
                    )
            except BackupArchiveError:
                raise
            except tarfile.TarError as exc:
                raise BackupArchiveError(
                    "Home Assistant component archive is not structurally readable"
                ) from exc

            if data_file_count < 1:
                raise BackupArchiveError(
                    "Home Assistant component archive does not contain configuration data files"
                )
    except BackupArchiveError:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise BackupArchiveError("downloaded Supervisor backup tar is not structurally readable") from exc

    return {
        "outer_tar_readable": True,
        "outer_member_count": outer_count,
        "backup_metadata_present": True,
        "backup_identity_verified": expected_slug is not None and expected_name is not None,
        "homeassistant_archive_present": True,
        "homeassistant_archive_readable": True,
        "homeassistant_member_count": inner_count,
        "homeassistant_metadata_present": True,
        "homeassistant_version_matches_api": expected_homeassistant_version is not None,
        "homeassistant_data_files": data_file_count,
    }
