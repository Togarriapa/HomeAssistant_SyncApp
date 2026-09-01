from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import os
from pathlib import Path
import stat
from typing import Iterator

from .policy import is_allowed_relative


class LiveFilesystemError(RuntimeError):
    pass


def _sha256_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


class LiveFilesystem:
    """Descriptor-relative access to the live Home Assistant configuration tree.

    Every parent component is opened with O_NOFOLLOW and subsequent leaf
    operations are relative to the already-open parent descriptor.  This keeps
    a concurrent pathname/symlink swap from redirecting a mutation outside the
    directory tree that was actually opened.
    """

    def __init__(self, root: Path):
        self.root = root

    def _open_root(self) -> int:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            return os.open(self.root, flags)
        except OSError as exc:
            raise LiveFilesystemError(f"cannot open live configuration root safely: {exc}") from exc

    @staticmethod
    def _parts(relative: str) -> tuple[str, ...]:
        if not is_allowed_relative(relative):
            raise LiveFilesystemError(f"blocked live path in transaction: {relative}")
        parts = Path(relative).parts
        if not parts:
            raise LiveFilesystemError("empty live path in transaction")
        return parts

    @contextmanager
    def _open_parent(self, relative: str, *, create: bool = False) -> Iterator[tuple[int, str]]:
        parts = self._parts(relative)
        current = self._open_root()
        try:
            for part in parts[:-1]:
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                try:
                    child = os.open(part, flags, dir_fd=current)
                except FileNotFoundError:
                    if not create:
                        raise LiveFilesystemError(
                            f"live parent directory does not exist: {relative}"
                        )
                    try:
                        os.mkdir(part, mode=0o755, dir_fd=current)
                        os.fsync(current)
                        child = os.open(part, flags, dir_fd=current)
                    except OSError as exc:
                        raise LiveFilesystemError(
                            f"cannot create live parent directory safely: {relative}: {exc}"
                        ) from exc
                except OSError as exc:
                    raise LiveFilesystemError(
                        f"refusing unsafe live parent component: {relative}: {exc}"
                    ) from exc
                os.close(current)
                current = child
            yield current, parts[-1]
        finally:
            os.close(current)

    def exists_regular(self, relative: str) -> bool:
        try:
            with self._open_parent(relative) as (parent_fd, leaf):
                try:
                    info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return False
                if not stat.S_ISREG(info.st_mode):
                    raise LiveFilesystemError(f"live target is not a regular file: {relative}")
                return True
        except LiveFilesystemError as exc:
            if "parent directory does not exist" in str(exc):
                return False
            raise

    def sha256(self, relative: str) -> str:
        with self._open_parent(relative) as (parent_fd, leaf):
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(leaf, flags, dir_fd=parent_fd)
            except OSError as exc:
                raise LiveFilesystemError(f"cannot read live regular file safely: {relative}: {exc}") from exc
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    raise LiveFilesystemError(f"live target is not a regular file: {relative}")
                return _sha256_fd(fd)
            finally:
                os.close(fd)

    def replace_from(self, relative: str, source: Path, expected_sha256: str) -> None:
        if source.is_symlink() or not source.is_file():
            raise LiveFilesystemError(f"replacement source is not a regular file: {relative}")

        with self._open_parent(relative, create=True) as (parent_fd, leaf):
            temporary = f".{leaf}.syncapp-new"
            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                temp_fd = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
            except FileExistsError as exc:
                raise LiveFilesystemError(
                    f"refusing pre-existing live transaction temporary file: {relative}"
                ) from exc
            except OSError as exc:
                raise LiveFilesystemError(f"cannot create live temporary file: {relative}: {exc}") from exc

            try:
                digest = hashlib.sha256()
                with source.open("rb") as source_handle:
                    while True:
                        chunk = source_handle.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        view = memoryview(chunk)
                        while view:
                            written = os.write(temp_fd, view)
                            view = view[written:]
                if digest.hexdigest() != expected_sha256:
                    raise LiveFilesystemError(f"staged content changed while copying: {relative}")
                os.fchmod(temp_fd, stat.S_IMODE(source.stat().st_mode))
                os.fsync(temp_fd)
            finally:
                os.close(temp_fd)

            try:
                os.replace(
                    temporary,
                    leaf,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
                os.fsync(parent_fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass

    def delete(self, relative: str) -> bool:
        try:
            with self._open_parent(relative) as (parent_fd, leaf):
                try:
                    info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return False
                if not stat.S_ISREG(info.st_mode):
                    raise LiveFilesystemError(f"refusing to delete non-file: {relative}")
                try:
                    os.unlink(leaf, dir_fd=parent_fd)
                except OSError as exc:
                    if exc.errno == errno.ENOENT:
                        return False
                    raise LiveFilesystemError(f"cannot delete live file safely: {relative}: {exc}") from exc
                os.fsync(parent_fd)
                return True
        except LiveFilesystemError as exc:
            if "parent directory does not exist" in str(exc):
                return False
            raise
