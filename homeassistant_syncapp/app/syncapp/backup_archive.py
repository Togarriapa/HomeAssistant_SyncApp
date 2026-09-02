from __future__ import annotations

from pathlib import Path, PurePosixPath
import tarfile


MAX_TAR_MEMBERS = 100_000
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


def verify_backup_archive(path: Path) -> dict[str, object]:
    """Verify a downloaded Supervisor backup without extracting configuration data."""
    outer_count = 0
    backup_json_count = 0
    homeassistant_members: list[tarfile.TarInfo] = []

    try:
        with tarfile.open(path, mode="r:*") as outer:
            for member in outer:
                outer_count = _count_member(outer_count)
                name = _safe_member_name(member.name)
                if name == "backup.json":
                    if not member.isfile() or member.size <= 0:
                        raise BackupArchiveError(
                            "backup.json is not a non-empty regular archive member"
                        )
                    backup_json_count += 1
                elif name in _HOMEASSISTANT_ARCHIVES:
                    if not member.isfile() or member.size <= 0:
                        raise BackupArchiveError(
                            "Home Assistant backup payload is not a non-empty regular member"
                        )
                    homeassistant_members.append(member)

            if backup_json_count != 1:
                raise BackupArchiveError(
                    "downloaded backup does not contain exactly one backup.json"
                )
            if len(homeassistant_members) != 1:
                raise BackupArchiveError(
                    "downloaded backup does not contain exactly one Home Assistant archive"
                )

            inner_stream = outer.extractfile(homeassistant_members[0])
            if inner_stream is None:
                raise BackupArchiveError("cannot read the Home Assistant backup archive member")

            inner_count = 0
            homeassistant_json_count = 0
            data_file_count = 0
            try:
                with inner_stream, tarfile.open(fileobj=inner_stream, mode="r:*") as inner:
                    for member in inner:
                        inner_count = _count_member(inner_count)
                        name = _safe_member_name(member.name)
                        if name == "homeassistant.json":
                            if not member.isfile() or member.size <= 0:
                                raise BackupArchiveError(
                                    "homeassistant.json is not a non-empty regular archive member"
                                )
                            homeassistant_json_count += 1
                        elif name.startswith("data/") and member.isfile():
                            data_file_count += 1
            except tarfile.TarError as exc:
                raise BackupArchiveError(
                    "Home Assistant component archive is not structurally readable"
                ) from exc

            if homeassistant_json_count != 1:
                raise BackupArchiveError(
                    "Home Assistant component archive does not contain exactly one homeassistant.json"
                )
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
        "homeassistant_archive_present": True,
        "homeassistant_archive_readable": True,
        "homeassistant_member_count": inner_count,
        "homeassistant_metadata_present": True,
        "homeassistant_data_files": data_file_count,
    }
