from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from .policy import is_allowed_relative


_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_BACKUP_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ALLOWED_STATES = {
    "preparing",
    "prepared",
    "backed_up",
    "applying",
    "applied",
    "configuration_valid",
    "restarting",
    "verified",
    "rolling_back",
    "rolled_back",
    "rollback_failed",
    "rollback_health_failed",
    "completed",
    "verified_drift",
}
_STATES_REQUIRING_COMPLETE_SNAPSHOT = _ALLOWED_STATES - {"preparing"}


class JournalIntegrityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JournalRecord:
    version: int
    state: str
    commit: str
    write_paths: tuple[str, ...]
    delete_paths: tuple[str, ...]
    write_sha256: tuple[tuple[str, str], ...]
    existed: frozenset[str]
    supervisor_backup: str | None


def journal_digest(payload: dict[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("integrity_sha256", None)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def attach_journal_digest(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["integrity_sha256"] = journal_digest(result)
    return result


def _path_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise JournalIntegrityError(f"{field} must be an array of strings")
    paths = tuple(value)
    if len(paths) != len(set(paths)):
        raise JournalIntegrityError(f"{field} contains duplicate paths")
    for relative in paths:
        if not is_allowed_relative(relative):
            raise JournalIntegrityError(f"{field} contains blocked or unsafe path: {relative}")
    return paths


def _snapshot_paths(snapshot_dir: Path) -> set[str]:
    if snapshot_dir.is_symlink():
        raise JournalIntegrityError("transaction snapshot root must not be a symlink")
    if not snapshot_dir.is_dir():
        raise JournalIntegrityError("transaction snapshot directory is missing")

    found: set[str] = set()
    for directory, dirnames, filenames in os.walk(snapshot_dir, followlinks=False):
        directory_path = Path(directory)
        for dirname in dirnames:
            child = directory_path / dirname
            if child.is_symlink():
                raise JournalIntegrityError("transaction snapshot contains a symlinked directory")
        for filename in filenames:
            child = directory_path / filename
            if child.is_symlink() or not child.is_file():
                raise JournalIntegrityError("transaction snapshot contains a non-regular file")
            relative = child.relative_to(snapshot_dir).as_posix()
            if not is_allowed_relative(relative):
                raise JournalIntegrityError(
                    f"transaction snapshot contains blocked or unsafe path: {relative}"
                )
            found.add(relative)
    return found


def validate_journal_payload(data: object, snapshot_dir: Path) -> JournalRecord:
    if not isinstance(data, dict):
        raise JournalIntegrityError("transaction journal must contain a JSON object")

    version = data.get("version")
    if version not in {1, 2}:
        raise JournalIntegrityError("unsupported transaction journal version")
    if version == 2:
        digest = data.get("integrity_sha256")
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            raise JournalIntegrityError("transaction journal integrity digest is missing or invalid")
        if not hashlib.compare_digest(digest, journal_digest(data)):
            raise JournalIntegrityError("transaction journal integrity digest does not match")

    state = data.get("state")
    if not isinstance(state, str) or state not in _ALLOWED_STATES:
        raise JournalIntegrityError("transaction journal contains an unsupported state")

    commit = data.get("commit")
    if not isinstance(commit, str) or not _SHA_RE.fullmatch(commit):
        raise JournalIntegrityError("transaction journal contains an invalid commit identifier")

    write_paths = _path_tuple(data.get("write_paths"), "write_paths")
    delete_paths = _path_tuple(data.get("delete_paths"), "delete_paths")
    overlap = set(write_paths) & set(delete_paths)
    if overlap:
        raise JournalIntegrityError(
            "transaction journal writes and deletes the same path: " + ", ".join(sorted(overlap))
        )
    affected = set(write_paths) | set(delete_paths)
    if not affected:
        raise JournalIntegrityError("transaction journal has an empty apply plan")

    raw_hashes = data.get("write_sha256", {})
    if not isinstance(raw_hashes, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw_hashes.items()
    ):
        raise JournalIntegrityError("transaction journal contains an invalid staged-content hash map")
    for relative, digest in raw_hashes.items():
        if relative not in write_paths:
            raise JournalIntegrityError(
                f"transaction journal contains a hash for a non-write path: {relative}"
            )
        if not _DIGEST_RE.fullmatch(digest):
            raise JournalIntegrityError(
                f"transaction journal contains an invalid SHA-256 digest for {relative}"
            )
    if raw_hashes and set(raw_hashes) != set(write_paths):
        raise JournalIntegrityError("transaction journal staged-content hashes are incomplete")

    existed_paths = _path_tuple(data.get("existed", []), "existed")
    existed = frozenset(existed_paths)
    if not existed <= affected:
        raise JournalIntegrityError("transaction journal existed paths are outside the apply plan")

    backup = data.get("supervisor_backup")
    if backup is not None:
        if not isinstance(backup, str) or not _BACKUP_SLUG_RE.fullmatch(backup):
            raise JournalIntegrityError("transaction journal contains an invalid Supervisor backup slug")
    if state in {"preparing", "prepared"} and backup is not None:
        raise JournalIntegrityError(
            f"transaction journal state {state} must not claim a Supervisor backup"
        )

    if state in _STATES_REQUIRING_COMPLETE_SNAPSHOT:
        snapshot_paths = _snapshot_paths(snapshot_dir)
        if snapshot_paths != set(existed):
            missing = sorted(set(existed) - snapshot_paths)
            unexpected = sorted(snapshot_paths - set(existed))
            details: list[str] = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if unexpected:
                details.append("unexpected=" + ",".join(unexpected))
            raise JournalIntegrityError(
                "transaction snapshot does not match journal existed set"
                + (": " + " ".join(details) if details else "")
            )

    return JournalRecord(
        version=version,
        state=state,
        commit=commit,
        write_paths=write_paths,
        delete_paths=delete_paths,
        write_sha256=tuple(sorted(raw_hashes.items())),
        existed=existed,
        supervisor_backup=backup,
    )
