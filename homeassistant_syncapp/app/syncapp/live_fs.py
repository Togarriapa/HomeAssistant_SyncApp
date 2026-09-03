from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import os
from pathlib import Path
import shutil
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


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        stat.S_IFMT(info.st_mode),
    )


def _directory_identity(info: os.stat_result) -> tuple[int, int, int]:
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


class LiveFilesystem:
    """Descriptor-relative access to the live Home Assistant configuration tree."""

    def __init__(self, root: Path):
        self.root = root

    def _open_root(self) -> int:
        # Keep the established operator-facing error explicit. This pre-check is
        # diagnostic only; O_NOFOLLOW below remains the actual race-safe gate.
        if self.root.is_symlink():
            raise LiveFilesystemError("live configuration root must not be a symlink")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            return os.open(self.root, flags)
        except OSError as exc:
            raise LiveFilesystemError(
                f"cannot open live configuration root safely (symlinks are refused): {exc}"
            ) from exc

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
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                try:
                    child = os.open(part, flags, dir_fd=current)
                except FileNotFoundError:
                    if not create:
                        raise LiveFilesystemError(f"live parent directory does not exist: {relative}")
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
                        f"refusing unsafe live parent component (symlink or non-directory): {relative}: {exc}"
                    ) from exc
                os.close(current)
                current = child
            yield current, parts[-1]
        finally:
            os.close(current)

    @contextmanager
    def _open_replacement_source(
        self, relative: str, source: Path
    ) -> Iterator[tuple[int, int]]:
        """Open a staged/rollback source beneath its inferred root without pathname traversal.

        FileTransaction always passes ``source_root / relative``. Derive that root
        lexically from the already policy-approved relative path, then pin the root,
        every parent directory entry, and the leaf before bytes are copied. The
        complete directory-entry chain and leaf metadata are rechecked before the
        caller is allowed to replace live configuration.
        """

        parts = self._parts(relative)
        source = Path(source)
        source_root = source
        for _ in parts:
            source_root = source_root.parent
        if source_root.joinpath(*parts) != source:
            raise LiveFilesystemError(f"replacement source is not rooted at expected path: {relative}")
        if source_root.is_symlink():
            raise LiveFilesystemError(f"replacement source root must not be a symlink: {relative}")

        directory_flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        directory_fds: list[int] = []
        directory_links: list[tuple[int, str, tuple[int, int, int]]] = []
        source_fd: int | None = None
        try:
            try:
                root_fd = os.open(source_root, directory_flags)
            except OSError as exc:
                raise LiveFilesystemError(
                    f"cannot open replacement source root safely: {relative}: {exc}"
                ) from exc
            directory_fds.append(root_fd)
            root_info = os.fstat(root_fd)
            if not stat.S_ISDIR(root_info.st_mode):
                raise LiveFilesystemError(f"replacement source root is not a directory: {relative}")
            root_identity = _directory_identity(root_info)

            current = root_fd
            for part in parts[:-1]:
                try:
                    child = os.open(part, directory_flags, dir_fd=current)
                    child_info = os.fstat(child)
                    entry_info = os.stat(part, dir_fd=current, follow_symlinks=False)
                except OSError as exc:
                    raise LiveFilesystemError(
                        f"refusing unsafe replacement source parent: {relative}: {exc}"
                    ) from exc
                if not stat.S_ISDIR(child_info.st_mode) or _directory_identity(entry_info) != _directory_identity(
                    child_info
                ):
                    os.close(child)
                    raise LiveFilesystemError(
                        f"replacement source parent changed while opening: {relative}"
                    )
                directory_links.append((current, part, _directory_identity(child_info)))
                directory_fds.append(child)
                current = child

            leaf = parts[-1]
            try:
                source_fd = os.open(leaf, file_flags, dir_fd=current)
                initial_info = os.fstat(source_fd)
                initial_entry = os.stat(leaf, dir_fd=current, follow_symlinks=False)
            except OSError as exc:
                raise LiveFilesystemError(
                    f"cannot open replacement source safely (symlinks are refused): {relative}: {exc}"
                ) from exc
            if not stat.S_ISREG(initial_info.st_mode):
                raise LiveFilesystemError(f"replacement source is not a regular file: {relative}")
            initial_identity = _file_identity(initial_info)
            if _file_identity(initial_entry) != initial_identity:
                raise LiveFilesystemError(f"replacement source changed while opening: {relative}")

            yield source_fd, stat.S_IMODE(initial_info.st_mode)

            final_info = os.fstat(source_fd)
            try:
                final_entry = os.stat(leaf, dir_fd=current, follow_symlinks=False)
            except OSError as exc:
                raise LiveFilesystemError(
                    f"replacement source disappeared after reading: {relative}: {exc}"
                ) from exc
            if _file_identity(final_info) != initial_identity or _file_identity(final_entry) != initial_identity:
                raise LiveFilesystemError(f"replacement source changed while copying: {relative}")

            for parent_fd, name, expected_identity in directory_links:
                try:
                    entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                except OSError as exc:
                    raise LiveFilesystemError(
                        f"replacement source parent disappeared after reading: {relative}: {exc}"
                    ) from exc
                if _directory_identity(entry) != expected_identity:
                    raise LiveFilesystemError(
                        f"replacement source parent changed while copying: {relative}"
                    )

            try:
                final_root = os.stat(source_root, follow_symlinks=False)
            except OSError as exc:
                raise LiveFilesystemError(
                    f"replacement source root disappeared after reading: {relative}: {exc}"
                ) from exc
            if _directory_identity(final_root) != root_identity:
                raise LiveFilesystemError(f"replacement source root changed while copying: {relative}")
        finally:
            if source_fd is not None:
                os.close(source_fd)
            for descriptor in reversed(directory_fds):
                os.close(descriptor)

    def exists_regular(self, relative: str) -> bool:
        try:
            with self._open_parent(relative) as (parent_fd, leaf):
                try:
                    info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return False
                if not stat.S_ISREG(info.st_mode):
                    raise LiveFilesystemError(
                        f"live target is not a regular file (symlinks are refused): {relative}"
                    )
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
                raise LiveFilesystemError(
                    f"cannot read live regular file safely (symlinks are refused): {relative}: {exc}"
                ) from exc
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    raise LiveFilesystemError(f"live target is not a regular file: {relative}")
                return _sha256_fd(fd)
            finally:
                os.close(fd)

    def copy_to(self, relative: str, destination: Path) -> str:
        with self._open_parent(relative) as (parent_fd, leaf):
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                source_fd = os.open(leaf, flags, dir_fd=parent_fd)
            except OSError as exc:
                raise LiveFilesystemError(
                    f"cannot snapshot live file safely (symlinks are refused): {relative}: {exc}"
                ) from exc
            try:
                info = os.fstat(source_fd)
                if not stat.S_ISREG(info.st_mode):
                    raise LiveFilesystemError(f"live target is not a regular file: {relative}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with os.fdopen(os.dup(source_fd), "rb") as source_handle, destination.open("xb") as target:
                    shutil.copyfileobj(source_handle, target, length=1024 * 1024)
                    os.fchmod(target.fileno(), stat.S_IMODE(info.st_mode))
                    target.flush()
                    os.fsync(target.fileno())
                snapshot_digest = _sha256_path(destination)
                if _sha256_fd(source_fd) != snapshot_digest:
                    raise LiveFilesystemError(
                        f"live configuration changed while rollback snapshot was being captured: {relative}"
                    )
                return snapshot_digest
            finally:
                os.close(source_fd)

    def replace_from(self, relative: str, source: Path, expected_sha256: str) -> None:
        with self._open_parent(relative, create=True) as (parent_fd, leaf):
            temporary = f".{leaf}.syncapp-new"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                try:
                    temp_fd = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
                except FileExistsError as exc:
                    raise LiveFilesystemError(
                        f"refusing pre-existing live transaction temporary file: {relative}"
                    ) from exc
                except OSError as exc:
                    raise LiveFilesystemError(
                        f"cannot create live temporary file: {relative}: {exc}"
                    ) from exc
                try:
                    digest = hashlib.sha256()
                    with self._open_replacement_source(relative, source) as (source_fd, source_mode):
                        os.lseek(source_fd, 0, os.SEEK_SET)
                        while True:
                            chunk = os.read(source_fd, 1024 * 1024)
                            if not chunk:
                                break
                            digest.update(chunk)
                            view = memoryview(chunk)
                            while view:
                                written = os.write(temp_fd, view)
                                view = view[written:]
                        if digest.hexdigest() != expected_sha256:
                            raise LiveFilesystemError(f"staged content changed while copying: {relative}")
                        os.fchmod(temp_fd, source_mode)
                        os.fsync(temp_fd)
                finally:
                    os.close(temp_fd)
                os.replace(temporary, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
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
                    raise LiveFilesystemError(
                        f"refusing to delete non-file (symlinks are refused): {relative}"
                    )
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
