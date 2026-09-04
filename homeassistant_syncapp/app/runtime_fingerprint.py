from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Protocol


DEFAULT_APP_ROOT = Path("/app")
DEFAULT_ENTRYPOINT = Path("/run.sh")
FINGERPRINT_SCHEMA = "syncapp-runtime-v1"


class Digest(Protocol):
    def update(self, data: bytes) -> None: ...


def _open_regular_no_follow(path: Path) -> int:
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("platform lacks O_NOFOLLOW support")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise RuntimeError(f"cannot open runtime fingerprint input safely: {path}: {exc}") from exc
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise RuntimeError(f"runtime fingerprint input is not a regular file: {path}")
    return fd


def _iter_app_files(app_root: Path) -> list[tuple[str, Path]]:
    if app_root.is_symlink() or not app_root.is_dir():
        raise RuntimeError("runtime app root must be a real directory")

    files: list[tuple[str, Path]] = []
    for directory, dirnames, filenames in os.walk(app_root, followlinks=False):
        directory_path = Path(directory)
        for dirname in tuple(dirnames):
            child = directory_path / dirname
            if child.is_symlink():
                raise RuntimeError(f"runtime app tree contains a symlink directory: {child}")
        for filename in filenames:
            path = directory_path / filename
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                raise RuntimeError(f"runtime app tree contains a symlink file: {path}")
            if not stat.S_ISREG(info.st_mode):
                raise RuntimeError(f"runtime app tree contains a non-regular file: {path}")
            relative = path.relative_to(app_root).as_posix()
            files.append((f"/app/{relative}", path))
    files.sort(key=lambda item: item[0])
    return files


def _hash_file(digest: Digest, label: str, path: Path) -> None:
    encoded_label = label.encode("utf-8")
    digest.update(len(encoded_label).to_bytes(4, "big"))
    digest.update(encoded_label)

    fd = _open_regular_no_follow(path)
    try:
        info = os.fstat(fd)
        digest.update(info.st_size.to_bytes(8, "big"))
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(fd)


def runtime_fingerprint(
    app_root: Path = DEFAULT_APP_ROOT,
    entrypoint: Path = DEFAULT_ENTRYPOINT,
) -> dict[str, object]:
    """Fingerprint exact image-owned runtime bytes for HAOS evidence correlation."""
    digest = hashlib.sha256()
    digest.update(FINGERPRINT_SCHEMA.encode("ascii") + b"\0")

    files = [("/run.sh", entrypoint), *_iter_app_files(app_root)]
    for label, path in files:
        _hash_file(digest, label, path)

    return {
        "schema": FINGERPRINT_SCHEMA,
        "algorithm": "sha256",
        "sha256": digest.hexdigest(),
        "files": len(files),
    }


def main() -> int:
    print(json.dumps(runtime_fingerprint(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
