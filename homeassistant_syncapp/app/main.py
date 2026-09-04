from __future__ import annotations

import logging
import signal
import time

from syncapp.config import Settings
from syncapp.engine import SyncEngine
from syncapp.runtime_environment import (
    configure_git_ca_trust,
    lock_git_tls_negotiation_defaults,
    scrub_ambient_git_tls_client_credentials,
    scrub_ambient_proxy_environment,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger("syncapp")
STOP = False


def _stop(_signum: int, _frame: object) -> None:
    global STOP
    STOP = True


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    scrub_ambient_proxy_environment()
    lock_git_tls_negotiation_defaults()
    scrub_ambient_git_tls_client_credentials()
    settings = Settings.load("/data/options.json")
    configure_git_ca_trust(settings.git_ca_bundle)
    engine = SyncEngine(settings)

    LOGGER.info(
        "Configured target=%s branch=%s dry_run=%s interval=%ss",
        settings.repository_url,
        settings.branch,
        settings.dry_run,
        settings.poll_interval_seconds,
    )

    while not STOP:
        try:
            engine.run_once()
        except Exception:
            LOGGER.exception("Synchronization cycle failed")

        deadline = time.monotonic() + settings.poll_interval_seconds
        while not STOP and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))

    LOGGER.info("Stopping HomeAssistant SyncApp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
