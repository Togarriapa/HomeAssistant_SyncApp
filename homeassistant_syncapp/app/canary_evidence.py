from __future__ import annotations

import argparse
import json
import re

from canary import DEFAULT_BACKUP_ARCHIVE_MAX_MIB, run_canary
from runtime_fingerprint import runtime_fingerprint
from syncapp.supervisor import SupervisorClient


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _verified_runtime_fingerprint(expected_sha256: str | None) -> dict[str, object]:
    evidence = runtime_fingerprint()
    observed = evidence.get("sha256")
    if not isinstance(observed, str) or not _SHA256_RE.fullmatch(observed):
        raise RuntimeError("runtime fingerprint did not produce a valid SHA-256 digest")
    if expected_sha256 is not None:
        expected = expected_sha256.strip().lower()
        if not _SHA256_RE.fullmatch(expected):
            raise RuntimeError("expected runtime SHA-256 must be exactly 64 lowercase hexadecimal characters")
        if observed != expected:
            raise RuntimeError(
                "runtime image fingerprint does not match the expected green CI image: "
                f"expected={expected}, observed={observed}"
            )
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind HomeAssistant SyncApp canary evidence to the exact runtime image bytes "
            "before exercising Supervisor/filesystem integration."
        )
    )
    parser.add_argument(
        "--expected-runtime-sha256",
        help=(
            "expected SHA-256 emitted by /app/runtime_fingerprint.py in the exact green "
            "candidate's Docker CI job; mismatch fails before any canary operation"
        ),
    )
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--backup-archive-probe", action="store_true")
    parser.add_argument(
        "--backup-archive-max-mib",
        type=int,
        default=DEFAULT_BACKUP_ARCHIVE_MAX_MIB,
    )
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--filesystem", action="store_true")
    parser.add_argument("--filesystem-write-probe", action="store_true")
    parser.add_argument("--filesystem-path", default="configuration.yaml")
    parser.add_argument("--timeout", type=int, default=120)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if not 30 <= args.timeout <= 600:
        parser.error("--timeout must be between 30 and 600 seconds")
    if not 16 <= args.backup_archive_max_mib <= 8192:
        parser.error("--backup-archive-max-mib must be between 16 and 8192")
    if args.restart and not args.backup:
        parser.error("--restart requires --backup")
    if args.backup_archive_probe and not args.backup:
        parser.error("--backup-archive-probe requires --backup")

    runtime = _verified_runtime_fingerprint(args.expected_runtime_sha256)
    result = run_canary(
        SupervisorClient(),
        create_backup=args.backup,
        backup_archive_probe=args.backup_archive_probe,
        backup_archive_max_bytes=args.backup_archive_max_mib * 1024 * 1024,
        restart=args.restart,
        timeout_seconds=args.timeout,
        filesystem=args.filesystem,
        filesystem_write_probe=args.filesystem_write_probe,
        filesystem_path=args.filesystem_path,
    )
    print(json.dumps({"runtime_image": runtime, **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
