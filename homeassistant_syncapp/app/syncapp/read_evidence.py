from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat


class ReadEvidenceError(RuntimeError):
    pass


def _stable_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _relative_parts(relative: str) -> tuple[str, ...]:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ReadEvidenceError(f"unsafe evidence path: {relative}")
    return path.parts


class PinnedReadRoot:
    """Read regular files beneath one no-follow, identity-pinned directory root."""

    def __init__(
        self,
        root: Path,
        *,
        expected_identity: tuple[int, int] | None = None,
        label: str = "evidence",
    ) -> None:
        self.root = root
        self.expected_identity = expected_identity
        self.label = label
        self._fd: int | None = None
        self._identity: tuple[int, int] | None = None

    def __enter__(self) -> "PinnedReadRoot":
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.root, flags)
        except OSError as exc:
            raise ReadEvidenceError(f"cannot open {self.label} root safely: {exc}") from exc
        try:
            info = os.fstat(fd)
            identity = (info.st_dev, info.st_ino)
            if not stat.S_ISDIR(info.st_mode) or (
                self.expected_identity is not None and identity != self.expected_identity
            ):
                raise ReadEvidenceError(
                    f"{self.label} root no longer identifies validated evidence"
                )
            self._fd = fd
            self._identity = identity
            self.assert_path_identity()
            return self
        except Exception:
            if self._fd == fd:
                self._fd = None
                self._identity = None
            os.close(fd)
            raise

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
        self._fd = None
        self._identity = None

    def _require_open(self) -> tuple[int, tuple[int, int]]:
        if self._fd is None or self._identity is None:
            raise ReadEvidenceError(f"{self.label} root is not open")
        return self._fd, self._identity

    def assert_path_identity(self) -> None:
        _, identity = self._require_open()
        try:
            current = os.stat(self.root, follow_symlinks=False)
        except OSError as exc:
            raise ReadEvidenceError(
                f"{self.label} root pathname disappeared during revalidation: {exc}"
            ) from exc
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != identity:
            raise ReadEvidenceError(f"{self.label} root pathname was replaced during revalidation")

    def sha256(self, relative: str) -> str:
        root_fd, _ = self._require_open()
        parts = _relative_parts(relative)
        directory_flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        opened_dirs: list[int] = []
        parent_chain: list[tuple[int, str, os.stat_result]] = []
        parent_fd = root_fd
        try:
            for name in parts[:-1]:
                child_fd: int | None = None
                try:
                    entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    child_fd = os.open(name, directory_flags, dir_fd=parent_fd)
                    opened = os.fstat(child_fd)
                except OSError as exc:
                    if child_fd is not None:
                        os.close(child_fd)
                    raise ReadEvidenceError(
                        f"cannot open {self.label} parent {name} safely: {exc}"
                    ) from exc
                if (
                    not stat.S_ISDIR(entry.st_mode)
                    or not stat.S_ISDIR(opened.st_mode)
                    or (entry.st_dev, entry.st_ino) != (opened.st_dev, opened.st_ino)
                ):
                    os.close(child_fd)
                    raise ReadEvidenceError(
                        f"{self.label} parent {name} was replaced while being opened"
                    )
                parent_chain.append((parent_fd, name, opened))
                opened_dirs.append(child_fd)
                parent_fd = child_fd

            leaf = parts[-1]
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                entry = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                fd = os.open(leaf, flags, dir_fd=parent_fd)
            except OSError as exc:
                raise ReadEvidenceError(
                    f"cannot open {self.label} file {relative} safely: {exc}"
                ) from exc
            try:
                before = os.fstat(fd)
                if (
                    not stat.S_ISREG(entry.st_mode)
                    or not stat.S_ISREG(before.st_mode)
                    or (entry.st_dev, entry.st_ino) != (before.st_dev, before.st_ino)
                ):
                    raise ReadEvidenceError(
                        f"{self.label} file {relative} changed type or identity while being opened"
                    )

                digest = hashlib.sha256()
                total = 0
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    total += len(chunk)

                after = os.fstat(fd)
                if _stable_identity(before) != _stable_identity(after) or total != after.st_size:
                    raise ReadEvidenceError(f"{self.label} file {relative} changed while being read")
                current_leaf = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    not stat.S_ISREG(current_leaf.st_mode)
                    or _stable_identity(current_leaf) != _stable_identity(after)
                ):
                    raise ReadEvidenceError(
                        f"{self.label} file {relative} was replaced while being read"
                    )
            finally:
                os.close(fd)

            for ancestor_fd, name, expected in reversed(parent_chain):
                current = os.stat(name, dir_fd=ancestor_fd, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(current.st_mode)
                    or _stable_identity(current) != _stable_identity(expected)
                ):
                    raise ReadEvidenceError(
                        f"{self.label} parent {name} was replaced while evidence was being read"
                    )
            self.assert_path_identity()
            return digest.hexdigest()
        except OSError as exc:
            raise ReadEvidenceError(f"cannot revalidate {self.label} safely: {exc}") from exc
        finally:
            for fd in reversed(opened_dirs):
                os.close(fd)
