from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import stat

from syncapp.live_fs import LiveFilesystem, LiveFilesystemError
from syncapp.supervisor import SupervisorClient


DEFAULT_LIVE_ROOT = Path("/homeassistant")
CANARY_TEMP_PREFIX = ".syncapp-canary-"
CANARY_TEMP_SUFFIX = ".tmp"


def _selected_fields(data: dict, fields: tuple[str, ...]) -> dict[str, object]:
    return {field: data[field] for field in fields if field in data}


def _environment_evidence(client: SupervisorClient) -> dict[str, object]:
    """Return a shareable allowlisted environment fingerprint for canary evidence."""
    return {
        "core": _selected_fields(
            client.core_info(),
            ("version", "arch", "machine", "image"),
        ),
        "supervisor": _selected_fields(
            client.supervisor_info(),
            ("version", "arch"),
        ),
        "host": _selected_fields(
            client.host_info(),
            (
                "operating_system",
                "kernel",
                "agent_version",
                "deployment",
                "virtualization",
            ),
        ),
    }


def _canary_temp_names(root_fd: int) -> tuple[str, ...]:
    names = (
        name
        for name in os.listdir(root_fd)
        if name.startswith(CANARY_TEMP_PREFIX) and name.endswith(CANARY_TEMP_SUFFIX)
    )
    return tuple(sorted(names))


def run_filesystem_canary(
    root: Path = DEFAULT_LIVE_ROOT,
    *,
    probe_path: str = "configuration.yaml",
    write_probe: bool = False,
) -> dict[str, object]:
    """Probe the live HA mount without touching configuration content.

    The default probe is read-only. The explicit write probe creates only
    randomly named ``*.tmp`` files, which are blocked by SyncApp policy, and
    removes them before returning.
    """
    if root.is_symlink():
        raise RuntimeError("live configuration root must not be a symlink")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RuntimeError("platform lacks O_NOFOLLOW/O_DIRECTORY support")

    root_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        root_fd = os.open(root, root_flags)
    except OSError as exc:
        raise RuntimeError(f"cannot open live configuration root safely: {exc}") from exc

    try:
        root_info = os.fstat(root_fd)
        if not stat.S_ISDIR(root_info.st_mode):
            raise RuntimeError("live configuration root is not a directory")

        # Exercise dir_fd and no-follow support on the actual mounted root.
        dot_fd = os.open(".", root_flags, dir_fd=root_fd)
        try:
            dot_info = os.fstat(dot_fd)
            if not stat.S_ISDIR(dot_info.st_mode):
                raise RuntimeError("descriptor-relative live root probe is not a directory")
        finally:
            os.close(dot_fd)
        os.stat(".", dir_fd=root_fd, follow_symlinks=False)

        filesystem = LiveFilesystem(root)
        if not filesystem.exists_regular(probe_path):
            raise RuntimeError(
                f"filesystem probe path is not an existing policy-approved regular file: {probe_path}"
            )
        digest = filesystem.sha256(probe_path)
        if len(digest) != 64:
            raise RuntimeError("filesystem probe did not produce a complete SHA-256 digest")

        result: dict[str, object] = {
            "root_opened_no_follow": True,
            "descriptor_relative_open": True,
            "descriptor_relative_stat": True,
            "probe_path": probe_path,
            "probe_path_exists_regular": True,
            "probe_path_read_verified": True,
            "write_probe": False,
        }

        if write_probe:
            stale_before = _canary_temp_names(root_fd)
            if stale_before:
                raise RuntimeError(
                    "refusing filesystem write probe while stale .syncapp-canary-*.tmp "
                    f"evidence exists under the live root ({len(stale_before)} file(s)); "
                    "inspect and resolve it before continuing"
                )
            result.update(_run_filesystem_write_probe(root_fd))
            stale_after = _canary_temp_names(root_fd)
            if stale_after:
                raise RuntimeError(
                    "filesystem write probe returned with .syncapp-canary-*.tmp "
                    f"evidence still present ({len(stale_after)} file(s))"
                )
            result["stale_probe_files_before"] = 0
            result["stale_probe_files_after"] = 0
        return result
    except LiveFilesystemError as exc:
        raise RuntimeError(f"live filesystem canary failed: {exc}") from exc
    finally:
        os.close(root_fd)


def _create_owned_probe_file(root_fd: int, name: str) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        return os.open(name, flags, 0o600, dir_fd=root_fd)
    except FileExistsError as exc:
        raise RuntimeError(
            f"filesystem canary random probe name unexpectedly already exists: {name}"
        ) from exc


def _run_filesystem_write_probe(root_fd: int) -> dict[str, object]:
    """Prove descriptor-relative replace/unlink/fsync on the real live mount."""
    token = secrets.token_hex(12)
    source_name = f"{CANARY_TEMP_PREFIX}{token}{CANARY_TEMP_SUFFIX}"
    destination_name = f"{CANARY_TEMP_PREFIX}{token}-replaced{CANARY_TEMP_SUFFIX}"
    payload = secrets.token_bytes(64)
    created: set[str] = set()

    try:
        source_fd = _create_owned_probe_file(root_fd, source_name)
        created.add(source_name)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(source_fd, view)
                if written <= 0:
                    raise RuntimeError("filesystem write probe made no forward progress")
                view = view[written:]
            os.fsync(source_fd)
        finally:
            os.close(source_fd)

        # Reserve the destination with O_EXCL before replacement. This makes
        # os.replace overwrite only a file created by this canary invocation,
        # never an unrelated pre-existing path even in the vanishingly unlikely
        # event of a random-name collision.
        destination_fd = _create_owned_probe_file(root_fd, destination_name)
        created.add(destination_name)
        os.close(destination_fd)
        os.fsync(root_fd)

        os.replace(
            source_name,
            destination_name,
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
        )
        created.discard(source_name)
        os.fsync(root_fd)

        read_fd = os.open(destination_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            observed = bytearray()
            while len(observed) < len(payload):
                chunk = os.read(read_fd, len(payload) - len(observed))
                if not chunk:
                    break
                observed.extend(chunk)
            if bytes(observed) != payload:
                raise RuntimeError("descriptor-relative replacement verification mismatch")
        finally:
            os.close(read_fd)

        os.unlink(destination_name, dir_fd=root_fd)
        created.discard(destination_name)
        os.fsync(root_fd)
        return {
            "write_probe": True,
            "exclusive_source_reservation": True,
            "exclusive_destination_reservation": True,
            "descriptor_relative_replace": True,
            "descriptor_relative_unlink": True,
            "file_fsync": True,
            "directory_fsync": True,
            "write_probe_cleanup": True,
        }
    finally:
        cleanup_error: OSError | None = None
        cleanup_attempted = bool(created)
        for name in tuple(created):
            try:
                os.unlink(name, dir_fd=root_fd)
            except FileNotFoundError:
                pass
            except OSError as exc:
                cleanup_error = exc
        if cleanup_attempted:
            try:
                os.fsync(root_fd)
            except OSError as exc:
                cleanup_error = cleanup_error or exc
        if cleanup_error is not None:
            raise RuntimeError(
                "filesystem canary cleanup failed; inspect blocked "
                f"{CANARY_TEMP_PREFIX}*{CANARY_TEMP_SUFFIX} files: {cleanup_error}"
            ) from cleanup_error


def run_canary(
    client: SupervisorClient,
    *,
    create_backup: bool = False,
    restart: bool = False,
    timeout_seconds: int = 120,
    filesystem: bool = False,
    filesystem_write_probe: bool = False,
    filesystem_root: Path = DEFAULT_LIVE_ROOT,
    filesystem_path: str = "configuration.yaml",
) -> dict[str, object]:
    """Exercise real integration contracts without modifying HA config files."""
    result: dict[str, object] = {
        "environment": _environment_evidence(client),
        "core_api": client.core_api_health(),
        "configuration_check": client.check_core_configuration(),
    }

    if filesystem or filesystem_write_probe:
        result["filesystem"] = run_filesystem_canary(
            filesystem_root,
            probe_path=filesystem_path,
            write_probe=filesystem_write_probe,
        )

    if create_backup:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result["backup_slug"] = client.create_homeassistant_backup(
            f"SyncApp canary {stamp}"
        )

    if restart:
        client.restart_core()
        result["post_restart_core_api"] = client.wait_for_core_api(timeout_seconds)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate HomeAssistant SyncApp's Supervisor and filesystem integration "
            "without modifying Home Assistant configuration files."
        )
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="also create a synchronous partial Home Assistant backup",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="explicitly restart Home Assistant Core and wait for API health",
    )
    parser.add_argument(
        "--filesystem",
        action="store_true",
        help="read-only probe of descriptor-relative access to /homeassistant",
    )
    parser.add_argument(
        "--filesystem-write-probe",
        action="store_true",
        help=(
            "explicitly create/replace/delete only blocked random *.tmp files under "
            "/homeassistant to verify descriptor-relative mutation and fsync support"
        ),
    )
    parser.add_argument(
        "--filesystem-path",
        default="configuration.yaml",
        help="existing policy-approved regular file to read through the no-follow filesystem layer",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Core health timeout in seconds when --restart is used (default: 120)",
    )
    args = parser.parse_args()
    if not 30 <= args.timeout <= 600:
        parser.error("--timeout must be between 30 and 600 seconds")

    result = run_canary(
        SupervisorClient(),
        create_backup=args.backup,
        restart=args.restart,
        timeout_seconds=args.timeout,
        filesystem=args.filesystem,
        filesystem_write_probe=args.filesystem_write_probe,
        filesystem_path=args.filesystem_path,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
