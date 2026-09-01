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
    snapshot_sha256: tuple[tuple[str, str], ...]
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


def _digest_map(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(digest, str) for key, digest in value.items()
    ):
        raise JournalIntegrityError(f"{field} must be an object of path-to-SHA-256 strings")
    result = dict(value)
    for relative, digest in result.items():
        if not is_allowed_relative(relative):
            raise JournalIntegrityError(f"{field} contains blocked or unsafe path: {relative}")
        if not _DIGEST_RE.fullmatch(digest):
            raise JournalIntegrityError(f"{field} contains an invalid SHA-256 digest for {relative}")
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_hashes(snapshot_dir: Path) -> dict[str, str]:
    if snapshot_dir.is_symlink():
        raise JournalIntegrityError("transaction snapshot root must not be a symlink")
    if not snapshot_dir.is_dir():
        raise JournalIntegrityError("transaction snapshot directory is missing")

    found: dict[str, str] = {}
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
            found[relative] = _sha256_file(child)
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
        if digest != journal_digest(data):
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

    raw_hashes = _digest_map(data.get("write_sha256", {}), "write_sha256")
    for relative in raw_hashes:
        if relative not in write_paths:
            raise JournalIntegrityError(
                f"transaction journal contains a hash for a non-write path: {relative}"
            )
    if raw_hashes and set(raw_hashes) != set(write_paths):
        raise JournalIntegrityError("transaction journal staged-content hashes are incomplete")

    existed_paths = _path_tuple(data.get("existed", []), "existed")
    existed = frozenset(existed_paths)
    if not existed <= affected:
        raise JournalIntegrityError("transaction journal existed paths are outside the apply plan")

    raw_snapshot_hashes = _digest_map(data.get("snapshot_sha256", {}), "snapshot_sha256")
    if version == 1 and raw_snapshot_hashes:
        raise JournalIntegrityError("legacy transaction journal must not contain snapshot_sha256")
    if version == 2:
        if state == "preparing":
            if raw_snapshot_hashes:
                raise JournalIntegrityError(
                    "preparing transaction journal must not claim complete snapshot hashes"
                )
        elif set(raw_snapshot_hashes) != set(existed):
            raise JournalIntegrityError(
                "transaction journal snapshot hashes do not match the existed set"
            )

    backup = data.get("supervisor_backup")
    if backup is not None:
        if not isinstance(backup, str) or not _BACKUP_SLUG_RE.fullmatch(backup):
            raise JournalIntegrityError("transaction journal contains an invalid Supervisor backup slug")
    if state in {"preparing", "prepared"} and backup is not None:
        raise JournalIntegrityError(
            f"transaction journal state {state} must not claim a Supervisor backup"
        )

    if state in _STATES_REQUIRING_COMPLETE_SNAPSHOT:
        actual_snapshot_hashes = _snapshot_hashes(snapshot_dir)
        if set(actual_snapshot_hashes) != set(existed):
            missing = sorted(set(existed) - set(actual_snapshot_hashes))
            unexpected = sorted(set(actual_snapshot_hashes) - set(existed))
            details: list[str] = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if unexpected:
                details.append("unexpected=" + ",".join(unexpected))
            raise JournalIntegrityError(
                "transaction snapshot does not match journal existed set"
                + (": " + " ".join(details) if details else "")
            )
        if version == 2:
            changed = sorted(
                relative
                for relative, expected in raw_snapshot_hashes.items()
                if actual_snapshot_hashes.get(relative) != expected
            )
            if changed:
                raise JournalIntegrityError(
                    "transaction rollback snapshot content digest does not match for: "
                    + ", ".join(changed)
                )

    return JournalRecord(
        version=version,
        state=state,
        commit=commit,
        write_paths=write_paths,
        delete_paths=delete_paths,
        write_sha256=tuple(sorted(raw_hashes.items())),
        existed=existed,
        snapshot_sha256=tuple(sorted(raw_snapshot_hashes.items())),
        supervisor_backup=backup,
    )
