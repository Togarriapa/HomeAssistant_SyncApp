from __future__ import annotations

import re
from pathlib import Path

from .live_fs import LiveFilesystem, LiveFilesystemError
from .policy import is_allowed_relative
from .transaction import ApplyPlan, TransactionError


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def build_validated_apply_plan(
    validated_sha256: dict[str, str],
    baseline_paths: set[str],
    commit: str,
    *,
    live_dir: Path | None = None,
) -> ApplyPlan:
    """Build plan semantics from immutable validated path/hash evidence, not staging paths."""
    desired_paths = set(validated_sha256)
    for relative, digest in validated_sha256.items():
        if not is_allowed_relative(relative):
            raise TransactionError(
                f"blocked path reached validated apply planner: {relative}"
            )
        if not _SHA256_RE.fullmatch(digest):
            raise TransactionError(
                f"invalid validated staging digest reached apply planner: {relative}"
            )

    write_paths: list[str] = []
    live_fs = LiveFilesystem(live_dir) if live_dir is not None else None
    for relative in sorted(desired_paths):
        expected = validated_sha256[relative]
        if live_fs is None:
            write_paths.append(relative)
            continue
        try:
            exists = live_fs.exists_regular(relative)
            if not exists or live_fs.sha256(relative) != expected:
                write_paths.append(relative)
        except LiveFilesystemError as exc:
            raise TransactionError(
                f"cannot compare validated candidate to live configuration safely: {exc}"
            ) from exc

    return ApplyPlan(
        commit=commit,
        write_paths=tuple(write_paths),
        delete_paths=tuple(sorted(baseline_paths - desired_paths)),
        write_sha256=tuple(
            (relative, validated_sha256[relative]) for relative in write_paths
        ),
    )
