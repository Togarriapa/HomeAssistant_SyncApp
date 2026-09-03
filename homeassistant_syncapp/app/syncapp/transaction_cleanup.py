from __future__ import annotations

import os
from pathlib import Path
import stat


class TransactionCleanupError(RuntimeError):
    pass


def _directory_identity(info: os.stat_result) -> tuple[int, int, int]:
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


def _entry_identity(info: os.stat_result) -> tuple[int, int, int]:
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


def _clear_directory(dir_fd: int) -> None:
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        names = list(os.listdir(dir_fd))
    except OSError as exc:
        raise TransactionCleanupError(
            f"cannot inspect transaction directory during cleanup: {exc}"
        ) from exc

    for name in names:
        try:
            entry = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except OSError as exc:
            raise TransactionCleanupError(
                f"transaction cleanup entry {name!r} disappeared before removal: {exc}"
            ) from exc

        if stat.S_ISDIR(entry.st_mode):
            child_fd: int | None = None
            try:
                child_fd = os.open(name, directory_flags, dir_fd=dir_fd)
                opened = os.fstat(child_fd)
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or _directory_identity(opened) != _directory_identity(entry)
                ):
                    raise TransactionCleanupError(
                        f"transaction cleanup directory {name!r} changed while being opened"
                    )
                _clear_directory(child_fd)
                current = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                if _directory_identity(current) != _directory_identity(opened):
                    raise TransactionCleanupError(
                        f"transaction cleanup directory {name!r} was replaced before removal"
                    )
                os.rmdir(name, dir_fd=dir_fd)
                if os.fstat(child_fd).st_nlink != 0:
                    raise TransactionCleanupError(
                        f"transaction cleanup could not prove removal of directory {name!r}"
                    )
                os.fsync(dir_fd)
            except TransactionCleanupError:
                raise
            except OSError as exc:
                raise TransactionCleanupError(
                    f"cannot remove transaction directory {name!r} safely: {exc}"
                ) from exc
            finally:
                if child_fd is not None:
                    os.close(child_fd)
            continue

        if not (stat.S_ISREG(entry.st_mode) or stat.S_ISLNK(entry.st_mode)):
            raise TransactionCleanupError(
                f"refusing special transaction cleanup entry {name!r}"
            )
        try:
            current = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            if _entry_identity(current) != _entry_identity(entry):
                raise TransactionCleanupError(
                    f"transaction cleanup entry {name!r} was replaced before removal"
                )
            os.unlink(name, dir_fd=dir_fd)
            os.fsync(dir_fd)
        except TransactionCleanupError:
            raise
        except OSError as exc:
            raise TransactionCleanupError(
                f"cannot remove transaction entry {name!r} safely: {exc}"
            ) from exc


def remove_transaction_tree(root: Path, expected_identity: tuple[int, int]) -> None:
    """Remove only the transaction tree identified by expected_identity.

    Recursive deletion is performed through the exact opened root descriptor. The
    parent pathname is consulted only for the final empty-directory unlink, where
    its entry must still identify that same root immediately before removal.
    """
    parent = root.parent
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_fd: int | None = None
    root_fd: int | None = None
    try:
        try:
            parent_fd = os.open(parent, directory_flags)
            root_fd = os.open(root.name, directory_flags, dir_fd=parent_fd)
        except OSError as exc:
            raise TransactionCleanupError(
                f"cannot open transaction tree safely for cleanup: {exc}"
            ) from exc

        opened = os.fstat(root_fd)
        if not stat.S_ISDIR(opened.st_mode) or (opened.st_dev, opened.st_ino) != expected_identity:
            raise TransactionCleanupError(
                "transaction root no longer identifies the expected cleanup tree"
            )
        entry = os.stat(root.name, dir_fd=parent_fd, follow_symlinks=False)
        if _directory_identity(entry) != _directory_identity(opened):
            raise TransactionCleanupError(
                "transaction root changed while cleanup descriptors were being opened"
            )

        _clear_directory(root_fd)

        current = os.stat(root.name, dir_fd=parent_fd, follow_symlinks=False)
        if _directory_identity(current) != _directory_identity(opened):
            raise TransactionCleanupError(
                "transaction root was replaced during cleanup; replacement tree was not traversed"
            )
        try:
            os.rmdir(root.name, dir_fd=parent_fd)
        except OSError as exc:
            raise TransactionCleanupError(
                f"cannot remove emptied transaction root safely: {exc}"
            ) from exc
        if os.fstat(root_fd).st_nlink != 0:
            raise TransactionCleanupError(
                "transaction cleanup could not prove that the opened root itself was removed"
            )
        os.fsync(parent_fd)
    except TransactionCleanupError:
        raise
    except OSError as exc:
        raise TransactionCleanupError(f"transaction cleanup failed safely: {exc}") from exc
    finally:
        if root_fd is not None:
            os.close(root_fd)
        if parent_fd is not None:
            os.close(parent_fd)
