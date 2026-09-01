from __future__ import annotations

from fnmatch import fnmatch
import os
from pathlib import Path, PurePosixPath


BLOCKED_DIR_NAMES = {
    ".git",
    ".storage",
    ".cloud",
    "__pycache__",
    "backups",
    "deps",
    "tts",
}

BLOCKED_FILE_NAMES = {
    ".HA_VERSION",
    ".uuid",
    "secrets.yaml",
    "secrets.yml",
}

BLOCKED_GLOBS = (
    "*.db",
    "*.db-*",
    "*.sqlite",
    "*.sqlite3",
    "*.log",
    "*.log.*",
    "*.pid",
    "*.lock",
    "*.tmp",
    "*.pyc",
    "*.pyo",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
)


def is_allowed_relative(relative: str | PurePosixPath) -> bool:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts:
        return False
    if any(part in BLOCKED_DIR_NAMES for part in path.parts[:-1]):
        return False
    if path.name in BLOCKED_FILE_NAMES:
        return False
    return not any(fnmatch(path.name, pattern) for pattern in BLOCKED_GLOBS)


def collect_allowed_files(root: Path) -> set[str]:
    files: set[str] = set()
    for current, dirs, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirs[:] = [
            name
            for name in dirs
            if name not in BLOCKED_DIR_NAMES
            and not (current_path / name).is_symlink()
        ]

        for name in names:
            absolute = current_path / name
            if absolute.is_symlink() or not absolute.is_file():
                continue
            relative = absolute.relative_to(root).as_posix()
            if is_allowed_relative(relative):
                files.add(relative)
    return files
