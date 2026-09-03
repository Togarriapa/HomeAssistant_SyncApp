from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Iterator

from .policy import is_allowed_relative


class MirrorFilesystemError(RuntimeError):
    pass


class MirrorFilesystem:
    """Mutate an isolated Git worktree through one no-follow directory root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._fd: int | None = None
        self._identity: tuple[int, int] | None = None

    def __enter__(self) -> "MirrorFilesystem":
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.root, flags)
        except OSError as exc:
            raise MirrorFilesystemError(f"cannot open mirror root safely: {exc}") from exc
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            os.close(fd)
            raise MirrorFilesystemError("mirror root is not a directory")
        self._fd = fd
        self._identity = (info.st_dev, info.st_ino)
        try:
            self.assert_path_identity()
        except Exception:
            os.close(fd)
            self._fd = None
            self._identity = None
            raise
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
        self._fd = None
        self._identity = None

    def _require_open(self) -> tuple[int, tuple[int, int]]:
        if self._fd is None or self._identity is None:
            raise MirrorFilesystemError("mirror filesystem is not open")
        return self._fd, self._identity

    @staticmethod
    def _parts(relative: str) -> tuple[str, ...]:
        path = PurePosixPath(relative)
        if not relative or not is_allowed_relative(path):
            raise MirrorFilesystemError(f"blocked mirror path: {relative}")
        return path.parts

    def assert_path_identity(self) -> None:
        _, identity = self._require_open()
        try:
            current = os.stat(self.root, follow_symlinks=False)
        except OSError as exc:
            raise MirrorFilesystemError(f"mirror root pathname disappeared: {exc}") from exc
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != identity:
            raise MirrorFilesystemError("mirror root pathname was replaced")

    @contextmanager
    def _open_parent(self, relative: str, *, create: bool) -> Iterator[tuple[int, str]]:
        root_fd, _ = self._require_open()
        parts = self._parts(relative)
        current = os.dup(root_fd)
        try:
            for part in parts[:-1]:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                try:
                    child = os.open(part, flags, dir_fd=current)
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        os.mkdir(part, mode=0o755, dir_fd=current)
                        os.fsync(current)
                        child = os.open(part, flags, dir_fd=current)
                    except OSError as exc:
                        raise MirrorFilesystemError(
                            f"cannot create mirror parent safely for {relative}: {exc}"
                        ) from exc
                except OSError as exc:
                    raise MirrorFilesystemError(
                        f"refusing unsafe mirror parent for {relative}: {exc}"
                    ) from exc
                os.close(current)
                current = child
            yield current, parts[-1]
        finally:
            os.close(current)

    def replace_bytes(self, relative: str, content: bytes) -> None:
        with self._open_parent(relative, create=True) as (parent_fd, leaf):
            existing: os.stat_result | None
            try:
                existing = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            except OSError as exc:
                raise MirrorFilesystemError(f"cannot inspect mirror leaf {relative}: {exc}") from exc
            if existing is not None and not stat.S_ISREG(existing.st_mode):
                raise MirrorFilesystemError(f"refusing non-regular mirror leaf: {relative}")

            temp = f".{leaf}.syncapp-tmp"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(temp, flags, 0o600, dir_fd=parent_fd)
            except OSError as exc:
                raise MirrorFilesystemError(f"cannot create mirror temporary for {relative}: {exc}") from exc
            try:
                view = memoryview(content)
                while view:
                    written = os.write(fd, view)
                    view = view[written:]
                os.fsync(fd)
            except Exception:
                try:
                    os.unlink(temp, dir_fd=parent_fd)
                except OSError:
                    pass
                raise
            finally:
                os.close(fd)

            try:
                os.chmod(temp, stat.S_IMODE(existing.st_mode) if existing is not None else 0o644, dir_fd=parent_fd, follow_symlinks=False)
                os.replace(temp, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                os.fsync(parent_fd)
            except OSError as exc:
                try:
                    os.unlink(temp, dir_fd=parent_fd)
                except OSError:
                    pass
                raise MirrorFilesystemError(f"cannot replace mirror leaf {relative}: {exc}") from exc
        self.assert_path_identity()

    def delete(self, relative: str) -> None:
        try:
            with self._open_parent(relative, create=False) as (parent_fd, leaf):
                try:
                    info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return
                if not stat.S_ISREG(info.st_mode):
                    raise MirrorFilesystemError(f"refusing non-regular mirror deletion: {relative}")
                os.unlink(leaf, dir_fd=parent_fd)
                os.fsync(parent_fd)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise MirrorFilesystemError(f"cannot delete mirror path {relative}: {exc}") from exc
        self.assert_path_identity()
