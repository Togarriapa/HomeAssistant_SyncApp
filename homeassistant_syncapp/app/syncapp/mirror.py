from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from .mirror_fs import MirrorFilesystem, MirrorFilesystemError
from .policy import BLOCKED_DIR_NAMES, is_allowed_relative
from .read_evidence import PinnedReadRoot, ReadEvidenceError


MAX_MANIFEST_BYTES = 1024 * 1024


class ManifestError(RuntimeError):
    """Raised when persisted managed-path state cannot be trusted safely."""


def _open_manifest_parent(path: Path) -> tuple[int, tuple[int, int]]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path.parent, flags)
        info = os.fstat(descriptor)
    except OSError as exc:
        raise ManifestError(f"managed-path manifest parent is unsafe: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode):
        os.close(descriptor)
        raise ManifestError("managed-path manifest parent is not a directory")
    return descriptor, (info.st_dev, info.st_ino)


def _fsync_directory(path: Path, expected_identity: tuple[int, int] | None = None) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if expected_identity is not None and (info.st_dev, info.st_ino) != expected_identity:
            raise OSError("directory identity changed before durability proof")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def load_manifest(path: Path) -> set[str]:
    parent_fd, parent_identity = _open_manifest_parent(path)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path.name, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            return set()
        except OSError as exc:
            raise ManifestError(f"managed-path manifest could not be opened safely: {exc}") from exc

        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ManifestError("managed-path manifest must be a regular file")
            if before.st_size > MAX_MANIFEST_BYTES:
                raise ManifestError("managed-path manifest exceeds safe size limit")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_MANIFEST_BYTES:
                    raise ManifestError("managed-path manifest exceeds safe size limit")
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if (
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                or total != after.st_size
            ):
                raise ManifestError("managed-path manifest changed while being read")
        finally:
            os.close(descriptor)

        try:
            current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise ManifestError(f"managed-path manifest changed after read: {exc}") from exc
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (
            after.st_dev,
            after.st_ino,
        ):
            raise ManifestError("managed-path manifest pathname was replaced during read")

        parent_now = os.fstat(parent_fd)
        if (parent_now.st_dev, parent_now.st_ino) != parent_identity:
            raise ManifestError("managed-path manifest parent changed during read")
        try:
            value = json.loads(b"".join(chunks).decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ManifestError("managed-path manifest is not valid UTF-8") from exc
        except json.JSONDecodeError as exc:
            raise ManifestError("managed-path manifest is not valid JSON") from exc
    finally:
        os.close(parent_fd)

    if not isinstance(value, list):
        raise ManifestError("managed-path manifest must be a JSON array")

    files: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ManifestError("managed-path manifest entries must all be strings")
        if not item or not is_allowed_relative(item):
            raise ManifestError(
                f"managed-path manifest contains an unsafe or invalid path: {item!r}"
            )
        files.add(item)

    return files


def save_manifest(path: Path, files: set[str]) -> None:
    unsafe = sorted(item for item in files if not item or not is_allowed_relative(item))
    if unsafe:
        raise ManifestError(
            "refusing to persist unsafe managed paths: " + ", ".join(repr(item) for item in unsafe)
        )

    payload = (json.dumps(sorted(files), indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ManifestError("refusing oversized managed-path manifest")

    parent_fd, parent_identity = _open_manifest_parent(path)
    temporary_name = path.with_suffix(".tmp").name
    owned_temporary = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
            owned_temporary = True
        except FileExistsError as exc:
            raise ManifestError(
                "refusing pre-existing managed-path manifest temporary file"
            ) from exc
        except OSError as exc:
            raise ManifestError(
                f"managed-path manifest temporary could not be created safely: {exc}"
            ) from exc

        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

        current_parent = os.fstat(parent_fd)
        if (current_parent.st_dev, current_parent.st_ino) != parent_identity:
            raise ManifestError("managed-path manifest parent changed before replace")

        try:
            os.replace(
                temporary_name,
                path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            owned_temporary = False
            _fsync_directory(path.parent, parent_identity)
        except OSError as exc:
            raise ManifestError(
                f"managed-path manifest could not be persisted durably: {exc}"
            ) from exc
    finally:
        if owned_temporary:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError:
                pass
        os.close(parent_fd)


def mirror_local_configuration(
    source: Path,
    destination: Path,
    previous_managed: set[str],
) -> set[str]:
    unsafe_previous = sorted(
        item for item in previous_managed if not item or not is_allowed_relative(item)
    )
    if unsafe_previous:
        raise ManifestError(
            "refusing to mirror from unsafe managed paths: "
            + ", ".join(repr(item) for item in unsafe_previous)
        )

    try:
        with PinnedReadRoot(source, label="live configuration mirror") as evidence, MirrorFilesystem(
            destination
        ) as mirror:
            current_tuple = evidence.regular_files(
                skip_dir_names=frozenset(BLOCKED_DIR_NAMES),
                allow_file=lambda relative: is_allowed_relative(relative),
            )
            current = set(current_tuple)

            for relative in current_tuple:
                mirror.replace_bytes(relative, evidence.read_bytes(relative))

            final_tuple = evidence.regular_files(
                skip_dir_names=frozenset(BLOCKED_DIR_NAMES),
                allow_file=lambda relative: is_allowed_relative(relative),
            )
            if final_tuple != current_tuple:
                raise ManifestError("live configuration path set changed during local mirror")

            for relative in sorted(previous_managed - current, reverse=True):
                mirror.delete(relative)

            evidence.assert_path_identity()
            mirror.assert_path_identity()
    except (ReadEvidenceError, MirrorFilesystemError) as exc:
        raise ManifestError(f"local mirror confinement failed: {exc}") from exc

    return current
