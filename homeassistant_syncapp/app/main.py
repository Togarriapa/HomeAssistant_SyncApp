from __future__ import annotations

import logging
from pathlib import Path
import signal
import time

from syncapp.config import Settings
from syncapp.engine import SyncEngine
from syncapp.process_lock import ProcessLock, ProcessLockError


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger("syncapp")
STOP = False
DATA_ROOT = Path("/data")


def _stop(_signum: int, _frame: object) -> None:
    global STOP
    STOP = True


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    try:
        with ProcessLock(DATA_ROOT) as ownership:
            settings = Settings.load(DATA_ROOT / "options.json")
            engine = SyncEngine(settings)

            LOGGER.info(
                "Configured target=%s branch=%s dry_run=%s interval=%ss",
                settings.repository_url,
                settings.branch,
                settings.dry_run,
                settings.poll_interval_seconds,
            )

            while not STOP:
                ownership.assert_path_identity()
                try:
                    engine.run_once()
                except Exception:
                    LOGGER.exception("Synchronization cycle failed")

                deadline = time.monotonic() + settings.poll_interval_seconds
                while not STOP and time.monotonic() < deadline:
                    time.sleep(min(1.0, deadline - time.monotonic()))
    except ProcessLockError as exc:
        LOGGER.error("Refusing to start or continue without exclusive SyncApp process ownership: %s", exc)
        return 2

    LOGGER.info("Stopping HomeAssistant SyncApp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
