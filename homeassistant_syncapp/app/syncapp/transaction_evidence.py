from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path
import stat


MAX_TRANSACTION_JOURNAL_BYTES = 1024 * 1024


class TransactionEvidenceError(RuntimeError):
    pass


class TransactionEvidenceMissing(TransactionEvidenceError):
    pass


def _stable_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _assert_entry_identity(
    dir_fd: int,
    name: str,
    expected: os.stat_result,
    *,
    expect_directory: bool,
) -> None:
    try:
        current = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except OSError as exc:
        raise TransactionEvidenceError(
            f"transaction evidence entry {name} disappeared or became inaccessible while being read: {exc}"
        ) from exc

    expected_type_matches = (
        stat.S_ISDIR(expected.st_mode) if expect_directory else stat.S_ISREG(expected.st_mode)
    )
    current_type_matches = (
        stat.S_ISDIR(current.st_mode) if expect_directory else stat.S_ISREG(current.st_mode)
    )
    if (
        not expected_type_matches
        or not current_type_matches
        or _stable_identity(current) != _stable_identity(expected)
    ):
        raise TransactionEvidenceError(
            f"transaction evidence entry {name} was replaced or changed while being read"
        )


def _hash_regular_file_at(parent_fd: int, name: str) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise TransactionEvidenceError(
            f"cannot open rollback snapshot file {name} safely: {exc}"
        ) from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise TransactionEvidenceError(
                f"rollback snapshot entry {name} is not a regular file"
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
            raise TransactionEvidenceError(
                f"rollback snapshot file {name} changed while recovery evidence was being read"
            )
        _assert_entry_identity(parent_fd, name, after, expect_directory=False)
        return digest.hexdigest()
    finally:
        os.close(fd)


def _snapshot_hashes_from_dir(dir_fd: int, prefix: str = "") -> dict[str, str]:
    try:
        names = sorted(os.listdir(dir_fd))
    except OSError as exc:
        raise TransactionEvidenceError(
            f"cannot inspect rollback snapshot directory safely: {exc}"
        ) from exc

    found: dict[str, str] = {}
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    for name in names:
        try:
            entry = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except OSError as exc:
            raise TransactionEvidenceError(
                f"rollback snapshot entry {name} disappeared or became inaccessible: {exc}"
            ) from exc

        relative = f"{prefix}/{name}" if prefix else name
        if stat.S_ISDIR(entry.st_mode):
            try:
                child_fd = os.open(name, directory_flags, dir_fd=dir_fd)
            except OSError as exc:
                raise TransactionEvidenceError(
                    f"cannot open rollback snapshot directory {relative} safely: {exc}"
                ) from exc
            try:
                opened = os.fstat(child_fd)
                if not stat.S_ISDIR(opened.st_mode) or (
                    opened.st_dev,
                    opened.st_ino,
                ) != (entry.st_dev, entry.st_ino):
                    raise TransactionEvidenceError(
                        f"rollback snapshot directory {relative} changed while being opened"
                    )
                nested = _snapshot_hashes_from_dir(child_fd, relative)
                overlap = set(found) & set(nested)
                if overlap:
                    raise TransactionEvidenceError(
                        "rollback snapshot contains duplicate recovery paths"
                    )
                found.update(nested)
                _assert_entry_identity(dir_fd, name, opened, expect_directory=True)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(entry.st_mode):
            found[relative] = _hash_regular_file_at(dir_fd, name)
        else:
            raise TransactionEvidenceError(
                f"rollback snapshot entry {relative} is not a regular file or directory"
            )
    return found


class TransactionEvidenceRoot:
    """Descriptor-pinned access to recovery-critical transaction evidence."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._fd: int | None = None
        self._identity: tuple[int, int] | None = None
        self._snapshot_identity: tuple[int, int] | None = None

    def __enter__(self) -> "TransactionEvidenceRoot":
        if self.root.is_symlink():
            raise TransactionEvidenceError("transaction root must not be a symlink")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.root, flags)
        except FileNotFoundError as exc:
            raise TransactionEvidenceMissing("transaction root does not exist") from exc
        except OSError as exc:
            raise TransactionEvidenceError(
                f"cannot open transaction root safely (symlinks are refused): {exc}"
            ) from exc
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            os.close(fd)
            raise TransactionEvidenceError("transaction root is not a directory")
        self._fd = fd
        self._identity = (info.st_dev, info.st_ino)
        self._snapshot_identity = None
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
        self._fd = None
        self._identity = None
        self._snapshot_identity = None

    def _require_open(self) -> tuple[int, tuple[int, int]]:
        if self._fd is None or self._identity is None:
            raise TransactionEvidenceError("transaction evidence root is not open")
        return self._fd, self._identity

    def root_identity(self) -> tuple[int, int]:
        """Return the identity of the transaction root opened for evidence validation."""
        _, identity = self._require_open()
        return identity

    def assert_path_identity(self) -> None:
        _, identity = self._require_open()
        try:
            info = os.stat(self.root, follow_symlinks=False)
        except OSError as exc:
            raise TransactionEvidenceError(
                f"transaction root pathname no longer identifies the opened evidence: {exc}"
            ) from exc
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != identity:
            raise TransactionEvidenceError(
                "transaction root pathname was replaced while recovery evidence was being validated"
            )

    def _assert_child_identity(self, name: str, expected: os.stat_result) -> None:
        root_fd, _ = self._require_open()
        _assert_entry_identity(root_fd, name, expected, expect_directory=False)

    def read_journal_text(self, name: str = "journal.json") -> str | None:
        root_fd, _ = self._require_open()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(name, flags, dir_fd=root_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise TransactionEvidenceError(
                f"cannot open transaction journal safely (symlinks are refused): {exc}"
            ) from exc
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise TransactionEvidenceError(
                    "transaction journal is not a regular file"
                )
            if before.st_size > MAX_TRANSACTION_JOURNAL_BYTES:
                raise TransactionEvidenceError(
                    "transaction journal exceeds the recovery evidence size limit"
                )

            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(fd, min(64 * 1024, MAX_TRANSACTION_JOURNAL_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_TRANSACTION_JOURNAL_BYTES:
                    raise TransactionEvidenceError(
                        "transaction journal exceeds the recovery evidence size limit"
                    )

            after = os.fstat(fd)
            if _stable_identity(before) != _stable_identity(after) or total != after.st_size:
                raise TransactionEvidenceError(
                    "transaction journal changed while recovery evidence was being read"
                )
            self._assert_child_identity(name, after)
            raw = b"".join(chunks)
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise TransactionEvidenceError(
                    "transaction journal is not valid UTF-8"
                ) from exc
        finally:
            os.close(fd)

    def snapshot_hashes(self, name: str = "snapshot") -> dict[str, str]:
        root_fd, _ = self._require_open()
        self._snapshot_identity = None
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            snapshot_fd = os.open(name, flags, dir_fd=root_fd)
        except OSError as exc:
            raise TransactionEvidenceError(
                f"cannot open transaction rollback snapshot safely (symlinks are refused): {exc}"
            ) from exc
        try:
            opened = os.fstat(snapshot_fd)
            if not stat.S_ISDIR(opened.st_mode):
                raise TransactionEvidenceError(
                    "transaction rollback snapshot is not a directory"
                )
            hashes = _snapshot_hashes_from_dir(snapshot_fd)
            _assert_entry_identity(root_fd, name, opened, expect_directory=True)
            self._snapshot_identity = (opened.st_dev, opened.st_ino)
            return hashes
        finally:
            os.close(snapshot_fd)

    def validated_snapshot_identity(self) -> tuple[int, int] | None:
        """Return the root identity from a successfully validated snapshot traversal."""
        self._require_open()
        return self._snapshot_identity

    def list_names(self) -> list[str]:
        root_fd, _ = self._require_open()
        try:
            return list(os.listdir(root_fd))
        except OSError as exc:
            raise TransactionEvidenceError(
                f"cannot inspect transaction root contents safely: {exc}"
            ) from exc

    def remove_if_empty(self) -> bool:
        _, identity = self._require_open()
        if self.list_names():
            return False
        self.assert_path_identity()

        parent = self.root.parent
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            parent_fd = os.open(parent, flags)
        except OSError as exc:
            raise TransactionEvidenceError(
                f"cannot open transaction parent safely for orphan cleanup: {exc}"
            ) from exc
        try:
            try:
                child = os.stat(
                    self.root.name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise TransactionEvidenceError(
                    f"cannot verify empty transaction root before cleanup: {exc}"
                ) from exc
            if not stat.S_ISDIR(child.st_mode) or (child.st_dev, child.st_ino) != identity:
                raise TransactionEvidenceError(
                    "transaction root identity changed before orphan cleanup"
                )
            try:
                os.rmdir(self.root.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    raise TransactionEvidenceError(
                        "transaction root disappeared during orphan cleanup"
                    ) from exc
                raise TransactionEvidenceError(
                    f"cannot remove empty transaction root safely: {exc}"
                ) from exc
            return True
        finally:
            os.close(parent_fd)
