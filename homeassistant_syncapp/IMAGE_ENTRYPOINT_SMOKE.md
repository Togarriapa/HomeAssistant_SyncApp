# Built-image entrypoint smoke boundary

CI exercises the add-on container from its real Docker `CMD` through `/run.sh`, the Home Assistant base image's `#!/usr/bin/with-contenv bashio` interpreter chain, the shipped `process_bootstrap.py`, and the final pinned Python exec.

## Proven by CI

The entrypoint-boundary smoke replaces only the first `/usr/bin/python3` executable with a recorder. It proves that `/run.sh`:

- executes through the real image command path;
- replaces inherited executable search state with `PATH=/usr/bin:/bin`;
- removes the enumerated Python startup controls before Python starts;
- removes the enumerated ELF loader controls before Python starts;
- forces `PYTHONNOUSERSITE=1`;
- invokes `/usr/bin/python3 -E -s -B /app/process_bootstrap.py`;
- keeps `SUPERVISOR_TOKEN` in the environment rather than the argument vector.

A second full-startup smoke leaves `/usr/bin/python3` and `process_bootstrap.py` untouched and bind-mounts only `/app/main.py` with a harmless recorder. That test executes the complete real startup path and proves that the final long-lived process receives exactly the documented allowlist:

- `PATH=/usr/bin:/bin`;
- `PYTHONNOUSERSITE=1`;
- `SUPERVISOR_TOKEN` when inherited;
- `TZ`, `LANG`, and `LC_ALL` when inherited.

Hostile proxy, Git, Python-path, dynamic-loader, HOME, and unrelated container variables must be absent from that final service environment. The final recorder also proves the Supervisor token is not present in the application argument vector.

The existing in-image bootstrap-module smoke remains as focused unit-style evidence for the same allowlist and exec contract using the image's shipped interpreter.

Together, these checks cover the repository-built container boundary from Docker `CMD` to the final application exec without starting the SyncApp service loop.

## Not proven by CI

These smokes do **not** establish production Home Assistant OS or Supervisor behavior. They do not prove Supervisor API availability, `/core/check`, backup creation and retention, restart/health behavior, add-on mount semantics, rollback, interrupted transaction recovery, or real remote apply behavior.

Those remain acceptance evidence that must be collected on a disposable Home Assistant OS/Supervisor installation before the cumulative safety stack is considered production-ready.

The synchronization lifecycle remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. The smokes introduce no Git operation against `/homeassistant` and change no secret/runtime-file exclusion policy.
