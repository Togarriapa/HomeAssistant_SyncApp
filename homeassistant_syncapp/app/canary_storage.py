from __future__ import annotations

import argparse
import json
from pathlib import Path

from syncapp.canary_storage import (
    DEFAULT_ARCHIVE_MAX_BYTES,
    DEFAULT_DATA_ROOT,
    DEFAULT_FREE_RESERVE_BYTES,
    DEFAULT_LIVE_ROOT,
    run_backup_storage_probe,
)
from syncapp.supervisor import SupervisorClient


MIB = 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a fresh verified Home Assistant backup, download and byte-verify "
            "its policy-approved live configuration under /data, and record "
            "storage/timing evidence for disposable HAOS production-readiness testing."
        )
    )
    parser.add_argument(
        "--archive-max-mib",
        type=int,
        default=DEFAULT_ARCHIVE_MAX_BYTES // MIB,
        help="hard backup-download ceiling in MiB (default: 1024)",
    )
    parser.add_argument(
        "--free-reserve-mib",
        type=int,
        default=DEFAULT_FREE_RESERVE_BYTES // MIB,
        help="minimum free-space reserve that must remain beyond the ceiling (default: 256)",
    )
    args = parser.parse_args()

    if not 16 <= args.archive_max_mib <= 8192:
        parser.error("--archive-max-mib must be between 16 and 8192")
    if not 64 <= args.free_reserve_mib <= 8192:
        parser.error("--free-reserve-mib must be between 64 and 8192")

    result = run_backup_storage_probe(
        SupervisorClient(),
        data_root=Path(DEFAULT_DATA_ROOT),
        live_root=Path(DEFAULT_LIVE_ROOT),
        max_bytes=args.archive_max_mib * MIB,
        reserve_bytes=args.free_reserve_mib * MIB,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
