# Built-image entrypoint smoke boundary

The CI image smoke exercises the add-on container from its real Docker `CMD` through `/run.sh` and the Home Assistant base image's `#!/usr/bin/with-contenv bashio` interpreter chain.

The smoke replaces only the final `/usr/bin/python3` executable with a recorder. This lets CI inspect the exact environment and argument vector handed off by `/run.sh` without contacting Supervisor or entering the synchronization loop.

## Proven by CI

The built image must:

- execute the real `/run.sh` command path;
- replace an inherited executable-search path with `PATH=/usr/bin:/bin`;
- remove the enumerated Python startup controls before Python starts;
- remove the enumerated ELF loader controls before Python starts;
- force `PYTHONNOUSERSITE=1`;
- invoke the bootstrap as `/usr/bin/python3 -E -s -B /app/process_bootstrap.py`;
- keep `SUPERVISOR_TOKEN` in the environment rather than the argument vector.

A separate in-image bootstrap smoke then executes the shipped `process_bootstrap.py` module with the image's real Python interpreter and proves that the long-lived application process receives only the documented allowlisted environment.

Together, these checks cover the repository-built container boundary from Docker `CMD` to the final application exec without starting the service loop.

## Not proven by CI

This smoke does **not** establish production Home Assistant OS or Supervisor behavior. In particular, it does not prove Supervisor API availability, `/core/check`, backup creation and retention, restart/health behavior, add-on mount semantics, rollback, interrupted transaction recovery, or real remote apply behavior.

Those remain acceptance evidence that must be collected on a disposable Home Assistant OS/Supervisor installation before the cumulative safety stack is considered production-ready.

The synchronization lifecycle remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. The smoke introduces no Git operation against `/homeassistant` and changes no secret/runtime-file exclusion policy.
