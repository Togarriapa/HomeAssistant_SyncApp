from __future__ import annotations

import errno
import fcntl
import os
from pathlib import Path
import stat


class ProcessLockError(RuntimeError):
    pass


class ProcessLock:
    """Hold exclusive SyncApp ownership of one persistent data-root inode."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self._fd: int | None = None
        self._identity: tuple[int, int] | None = None

    def __enter__(self) -> "ProcessLock":
        if self.data_root.is_symlink():
            raise ProcessLockError("SyncApp data root must not be a symlink")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.data_root, flags)
        except OSError as exc:
            raise ProcessLockError(
                f"cannot open SyncApp data root safely for process ownership: {exc}"
            ) from exc

        try:
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode):
                raise ProcessLockError("SyncApp data root is not a directory")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise ProcessLockError(
                        "another SyncApp process already owns the persistent data root"
                    ) from exc
                raise ProcessLockError(
                    f"cannot acquire SyncApp process ownership lock: {exc}"
                ) from exc
            self._fd = fd
            self._identity = (info.st_dev, info.st_ino)
            return self
        except Exception:
            os.close(fd)
            raise

    def assert_path_identity(self) -> None:
        if self._fd is None or self._identity is None:
            raise ProcessLockError("SyncApp process ownership lock is not held")
        try:
            info = os.stat(self.data_root, follow_symlinks=False)
        except OSError as exc:
            raise ProcessLockError(
                f"SyncApp data-root pathname no longer identifies the locked directory: {exc}"
            ) from exc
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != self._identity:
            raise ProcessLockError(
                "SyncApp data-root pathname was replaced while process ownership was held"
            )

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        fd = self._fd
        self._fd = None
        self._identity = None
        if fd is None:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
