from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
from typing import IO


MAX_TAR_MEMBERS = 100_000
MAX_METADATA_BYTES = 1024 * 1024
MAX_OUTER_MEMBER_BYTES = 8 * 1024 * 1024 * 1024
MAX_OUTER_LOGICAL_BYTES = 16 * 1024 * 1024 * 1024
MAX_HOMEASSISTANT_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
MAX_HOMEASSISTANT_LOGICAL_BYTES = 8 * 1024 * 1024 * 1024
_HOMEASSISTANT_ARCHIVES = {"homeassistant.tar", "homeassistant.tar.gz"}


class BackupArchiveError(RuntimeError):
    pass


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise BackupArchiveError("backup archive contains an unsafe member name")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise BackupArchiveError("backup archive contains an unsafe member path")
    normalized = "/".join(part for part in path.parts if part not in {"", "."})
    if not normalized:
        raise BackupArchiveError("backup archive contains an empty normalized member path")
    return normalized


def _count_member(count: int) -> int:
    count += 1
    if count > MAX_TAR_MEMBERS:
        raise BackupArchiveError(
            f"backup archive exceeds the {MAX_TAR_MEMBERS} member safety limit"
        )
    return count


def _bounded_regular_size(
    total: int,
    member: tarfile.TarInfo,
    *,
    label: str = "Home Assistant component archive",
    max_member_bytes: int = MAX_HOMEASSISTANT_MEMBER_BYTES,
    max_total_bytes: int = MAX_HOMEASSISTANT_LOGICAL_BYTES,
) -> int:
    """Bound declared uncompressed regular-file work before advancing a tar stream."""
    if not member.isfile():
        return total
    if member.size < 0 or member.size > max_member_bytes:
        raise BackupArchiveError(
            f"{label} contains a regular member exceeding the "
            f"{max_member_bytes}-byte logical member limit"
        )
    total += member.size
    if total > max_total_bytes:
        raise BackupArchiveError(
            f"{label} exceeds the {max_total_bytes}-byte logical payload limit"
        )
    return total


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


def _validated_expected_hashes(
    expected: dict[str, str] | None,
) -> dict[str, str] | None:
    if expected is None:
        return None
    if not expected:
        raise BackupArchiveError("expected live-file backup coverage cannot be empty")
    validated: dict[str, str] = {}
    for relative, digest in expected.items():
        if not isinstance(relative, str) or not relative:
            raise BackupArchiveError("expected live-file path is empty or invalid")
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative or "\x00" in relative:
            raise BackupArchiveError("expected live-file path is unsafe")
        normalized = "/".join(part for part in path.parts if part not in {"", "."})
        if not normalized or normalized != relative:
            raise BackupArchiveError("expected live-file path is not canonical")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise BackupArchiveError("expected live-file SHA-256 digest is invalid")
        if normalized in validated:
            raise BackupArchiveError("duplicate expected live-file path")
        validated[normalized] = digest
    return validated


def _hash_member(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    stream = archive.extractfile(member)
    if stream is None:
        raise BackupArchiveError("cannot read expected Home Assistant backup data member")
    digest = hashlib.sha256()
    observed = 0
    with stream:
        while True:
            chunk = stream.read(min(1024 * 1024, member.size - observed + 1))
            if not chunk:
                break
            observed += len(chunk)
            if observed > member.size:
                raise BackupArchiveError("backup data member exceeds its declared size")
            digest.update(chunk)
    if observed != member.size:
        raise BackupArchiveError("backup data member is shorter than its declared size")
    return digest.hexdigest()


def verify_backup_archive(
    path: Path,
    *,
    expected_slug: str | None = None,
    expected_name: str | None = None,
    expected_homeassistant_version: str | None = None,
    expected_data_sha256: dict[str, str] | None = None,
) -> dict[str, object]:
    """Verify a downloaded Supervisor backup without extracting configuration data."""
    expected_hashes = _validated_expected_hashes(expected_data_sha256)
    outer_count = 0
    outer_logical_bytes = 0
    backup_json_members: list[tarfile.TarInfo] = []
    homeassistant_members: list[tarfile.TarInfo] = []

    try:
        with tarfile.open(path, mode="r:*") as outer:
            for member in outer:
                outer_count = _count_member(outer_count)
                name = _safe_member_name(member.name)
                outer_logical_bytes = _bounded_regular_size(
                    outer_logical_bytes,
                    member,
                    label="downloaded Supervisor backup archive",
                    max_member_bytes=MAX_OUTER_MEMBER_BYTES,
                    max_total_bytes=MAX_OUTER_LOGICAL_BYTES,
                )
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
            if backup_metadata.get("type") != "partial":
                raise BackupArchiveError(
                    "downloaded backup.json does not describe the requested partial backup"
                )
            homeassistant_metadata = backup_metadata.get("homeassistant")
            if not isinstance(homeassistant_metadata, dict):
                raise BackupArchiveError(
                    "downloaded backup.json does not describe Home Assistant content"
                )
            if homeassistant_metadata.get("exclude_database") is not True:
                raise BackupArchiveError(
                    "downloaded backup.json does not confirm Home Assistant database exclusion"
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
            inner_logical_bytes = 0
            homeassistant_json_members: list[tarfile.TarInfo] = []
            data_file_count = 0
            verified_expected: set[str] = set()
            try:
                with inner_stream, tarfile.open(fileobj=inner_stream, mode="r:*") as inner:
                    for member in inner:
                        inner_count = _count_member(inner_count)
                        name = _safe_member_name(member.name)
                        inner_logical_bytes = _bounded_regular_size(
                            inner_logical_bytes, member
                        )
                        if name == "homeassistant.json":
                            homeassistant_json_members.append(member)
                        elif name.startswith("data/") and member.isfile():
                            data_file_count += 1
                            relative = name.removeprefix("data/")
                            if expected_hashes is not None and relative in expected_hashes:
                                if relative in verified_expected:
                                    raise BackupArchiveError(
                                        "Home Assistant backup contains duplicate expected data path"
                                    )
                                if _hash_member(inner, member) != expected_hashes[relative]:
                                    raise BackupArchiveError(
                                        "Home Assistant backup data does not match live file bytes"
                                    )
                                verified_expected.add(relative)
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
            if expected_hashes is not None and verified_expected != set(expected_hashes):
                raise BackupArchiveError(
                    "Home Assistant backup is missing one or more expected live files"
                )
    except BackupArchiveError:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise BackupArchiveError("downloaded Supervisor backup tar is not structurally readable") from exc

    expected_count = len(expected_hashes) if expected_hashes is not None else 0
    return {
        "outer_tar_readable": True,
        "outer_member_count": outer_count,
        "outer_logical_bytes": outer_logical_bytes,
        "outer_logical_size_bounded": True,
        "backup_metadata_present": True,
        "backup_identity_verified": expected_slug is not None and expected_name is not None,
        "partial_backup_verified": True,
        "homeassistant_database_excluded": True,
        "homeassistant_archive_present": True,
        "homeassistant_archive_readable": True,
        "homeassistant_member_count": inner_count,
        "homeassistant_logical_bytes": inner_logical_bytes,
        "homeassistant_logical_size_bounded": True,
        "homeassistant_metadata_present": True,
        "homeassistant_version_matches_api": expected_homeassistant_version is not None,
        "homeassistant_data_files": data_file_count,
        "expected_live_files": expected_count,
        "expected_live_files_byte_verified": expected_hashes is not None,
    }
