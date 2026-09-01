from __future__ import annotations

import json
from pathlib import Path
import shutil

from .policy import collect_allowed_files


def load_manifest(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(item) for item in value if isinstance(item, str)}


def save_manifest(path: Path, files: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(sorted(files), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def mirror_local_configuration(
    source: Path,
    destination: Path,
    previous_managed: set[str],
) -> set[str]:
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
