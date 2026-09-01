from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json

from syncapp.supervisor import SupervisorClient


def run_canary(
    client: SupervisorClient,
    *,
    create_backup: bool = False,
    restart: bool = False,
    timeout_seconds: int = 120,
) -> dict[str, object]:
    """Exercise the real Supervisor contract without changing HA config files."""
    result: dict[str, object] = {
        "core_info": client.core_info(),
        "core_api": client.core_api_health(),
        "configuration_check": client.check_core_configuration(),
    }

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
            "Validate HomeAssistant SyncApp's Supervisor integration without modifying "
            "Home Assistant configuration files."
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
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
