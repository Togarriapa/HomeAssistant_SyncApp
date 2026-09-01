from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from .policy import collect_allowed_files, is_allowed_relative


class ManifestError(RuntimeError):
    """Raised when persisted managed-path state cannot be trusted safely."""


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def load_manifest(path: Path) -> set[str]:
    if not path.exists():
        return set()

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestError(f"managed-path manifest could not be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError("managed-path manifest is not valid JSON") from exc

    if not isinstance(value, list):
        raise ManifestError("managed-path manifest must be a JSON array")

    files: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ManifestError("managed-path manifest entries must all be strings")
        if not item or not is_allowed_relative(item):
            raise ManifestError(
                f"managed-path manifest contains an unsafe or invalid path: {item!r}"
            )
        files.add(item)

    return files


def save_manifest(path: Path, files: set[str]) -> None:
    unsafe = sorted(item for item in files if not item or not is_allowed_relative(item))
    if unsafe:
        raise ManifestError(
            "refusing to persist unsafe managed paths: " + ", ".join(repr(item) for item in unsafe)
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(sorted(files), indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ManifestError(
            f"managed-path manifest could not be persisted durably: {exc}"
        ) from exc


def mirror_local_configuration(
    source: Path,
    destination: Path,
    previous_managed: set[str],
) -> set[str]:
    unsafe_previous = sorted(
        item for item in previous_managed if not item or not is_allowed_relative(item)
    )
    if unsafe_previous:
        raise ManifestError(
            "refusing to mirror from unsafe managed paths: "
            + ", ".join(repr(item) for item in unsafe_previous)
        )

    current = collect_allowed_files(source)

    for relative in sorted(current):
        src = source / relative
        dst = destination / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for relative in sorted(previous_managed - current, reverse=True):
        target = destination / relative
        if target.is_file() or target.is_symlink():
            target.unlink()

    return current
