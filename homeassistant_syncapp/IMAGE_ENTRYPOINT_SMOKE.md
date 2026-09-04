# Built-image entrypoint smoke boundary

CI exercises the add-on container through its real Docker `CMD`, `/run.sh`, and the Home Assistant base image's `#!/usr/bin/with-contenv bashio` path.

The smoke replaces only the first `/usr/bin/python3` executable with a recorder. This proves the real shell boundary pins `PATH=/usr/bin:/bin`, removes the enumerated Python startup and ELF loader controls, forces `PYTHONNOUSERSITE=1`, invokes `/app/process_bootstrap.py` with `-E -s -B`, and keeps the Supervisor credential out of the argument vector.

A separate in-image bootstrap smoke executes the shipped bootstrap module with the image's real Python interpreter and verifies the documented long-lived environment allowlist.

These checks are repository/image evidence only. They do not prove Supervisor API behavior, `/core/check`, backup creation, restart/health, add-on mount semantics, rollback, interrupted transaction recovery, or real remote apply behavior. Those remain mandatory acceptance evidence on a disposable Home Assistant OS/Supervisor installation.

The synchronization lifecycle remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. The smoke performs no Git operation against `/homeassistant` and does not change any secret/runtime-file exclusion policy.
