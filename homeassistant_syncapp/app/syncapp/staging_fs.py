from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
from typing import Iterator

from .policy import is_allowed_relative


class StagingFilesystemError(RuntimeError):
    pass


class StagingFilesystem:
    """Keep staging materialization writes confined to one opened directory tree."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._root_fd: int | None = None
        self._root_identity: tuple[int, int] | None = None

    def __enter__(self) -> "StagingFilesystem":
        if self.root.is_symlink():
            raise StagingFilesystemError("staging root must not be a symlink")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            self._root_fd = os.open(self.root, flags)
        except OSError as exc:
            raise StagingFilesystemError(
                f"cannot open staging root safely (symlinks are refused): {exc}"
            ) from exc
        info = os.fstat(self._root_fd)
        if not stat.S_ISDIR(info.st_mode):
            os.close(self._root_fd)
            self._root_fd = None
            raise StagingFilesystemError("staging root is not a directory")
        self._root_identity = (info.st_dev, info.st_ino)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._root_fd is not None:
            os.close(self._root_fd)
        self._root_fd = None
        self._root_identity = None

    def _require_open(self) -> tuple[int, tuple[int, int]]:
        if self._root_fd is None or self._root_identity is None:
            raise StagingFilesystemError("staging filesystem is not open")
        return self._root_fd, self._root_identity

    def root_identity(self) -> tuple[int, int]:
        """Return the device/inode identity of the staging tree opened for materialization."""
        _, identity = self._require_open()
        return identity

    @staticmethod
    def _parts(relative: str) -> tuple[str, ...]:
        if not is_allowed_relative(relative):
            raise StagingFilesystemError(f"blocked staging path: {relative}")
        parts = Path(relative).parts
        if not parts:
            raise StagingFilesystemError("empty staging path")
        return parts

    @contextmanager
    def _open_parent(self, relative: str) -> Iterator[tuple[int, str]]:
        root_fd, _ = self._require_open()
        parts = self._parts(relative)
        current = os.dup(root_fd)
        try:
            for part in parts[:-1]:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                try:
                    child = os.open(part, flags, dir_fd=current)
                except FileNotFoundError:
                    try:
                        os.mkdir(part, mode=0o755, dir_fd=current)
                        os.fsync(current)
                        child = os.open(part, flags, dir_fd=current)
                    except OSError as exc:
                        raise StagingFilesystemError(
                            f"cannot create staging parent safely: {relative}: {exc}"
                        ) from exc
                except OSError as exc:
                    raise StagingFilesystemError(
                        f"refusing unsafe staging parent component: {relative}: {exc}"
                    ) from exc
                os.close(current)
                current = child
            yield current, parts[-1]
        finally:
            os.close(current)

    def write_new(self, relative: str, content: bytes, expected_sha256: str) -> None:
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise StagingFilesystemError(
                f"fetched Git blob hash changed before staging write: {relative}"
            )
        with self._open_parent(relative) as (parent_fd, leaf):
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(leaf, flags, 0o644, dir_fd=parent_fd)
            except FileExistsError as exc:
                raise StagingFilesystemError(
                    f"refusing pre-existing staging leaf: {relative}"
                ) from exc
            except OSError as exc:
                raise StagingFilesystemError(
                    f"cannot create staging leaf safely: {relative}: {exc}"
                ) from exc
            try:
                view = memoryview(content)
                while view:
                    written = os.write(fd, view)
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(parent_fd)

    def assert_path_identity(self, path: Path | None = None) -> None:
        _, identity = self._require_open()
        candidate = self.root if path is None else path
        try:
            info = os.stat(candidate, follow_symlinks=False)
        except OSError as exc:
            raise StagingFilesystemError(
                f"staging root pathname no longer identifies the opened tree: {exc}"
            ) from exc
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != identity:
            raise StagingFilesystemError(
                "staging root pathname was replaced while materialization was in progress"
            )
