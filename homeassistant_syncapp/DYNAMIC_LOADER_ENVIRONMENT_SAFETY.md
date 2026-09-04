# Dynamic loader environment safety

SyncApp's long-lived Python process and every later Git subprocess must not inherit ambient dynamic-loader controls that can change native library loading or redirect loader diagnostics/profile output.

Before `run.sh` replaces the add-on shell with `/usr/bin/python3`, it removes:

- `LD_PRELOAD`
- `LD_LIBRARY_PATH`
- `LD_AUDIT`
- `LD_DEBUG`
- `LD_DEBUG_OUTPUT`
- `LD_PROFILE`
- `LD_PROFILE_OUTPUT`

This means those inherited variables cannot control native code loading or loader-generated output for the Python process that executes SyncApp, nor for subprocesses it later launches.

## Bootstrap limitation

This is deliberately **not** described as a complete container-entrypoint loader sandbox. The `run.sh` shebang starts `/usr/bin/with-contenv` and its shell before the script body can execute, so a shell-level `unset` cannot retroactively protect those already-started executables from loader state supplied by the container runtime.

A complete pre-entrypoint guarantee would have to be enforced outside the script body, for example by the container/runtime environment contract or by an independently trusted launcher that cannot itself consume the hostile loader state. SyncApp must not claim that stronger property based only on this scrub.

## Relationship to the update workflow

This hardening does not change repository or Home Assistant data semantics. Remote updates remain:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git, no blind `git pull` is introduced, and all existing secret/runtime-file exclusions remain unchanged.
