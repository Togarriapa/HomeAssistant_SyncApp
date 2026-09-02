from __future__ import annotations

import errno
import os
from pathlib import Path
import stat


MAX_TRANSACTION_JOURNAL_BYTES = 1024 * 1024


class TransactionEvidenceError(RuntimeError):
    pass


class TransactionEvidenceMissing(TransactionEvidenceError):
    pass


class TransactionEvidenceRoot:
    """Descriptor-pinned access to recovery-critical transaction evidence."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._fd: int | None = None
        self._identity: tuple[int, int] | None = None

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
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
        self._fd = None
        self._identity = None

    def _require_open(self) -> tuple[int, tuple[int, int]]:
        if self._fd is None or self._identity is None:
            raise TransactionEvidenceError("transaction evidence root is not open")
        return self._fd, self._identity

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
            stable_before = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            stable_after = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            if stable_before != stable_after or total != after.st_size:
                raise TransactionEvidenceError(
                    "transaction journal changed while recovery evidence was being read"
                )
            raw = b"".join(chunks)
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise TransactionEvidenceError(
                    "transaction journal is not valid UTF-8"
                ) from exc
        finally:
            os.close(fd)

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
