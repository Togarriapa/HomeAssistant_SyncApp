# Python process environment allowlist

SyncApp does not let the long-lived Python service inherit the add-on container environment wholesale. `run.sh` first starts a minimal `/app/process_bootstrap.py` with the already established `/usr/bin/python3 -E -s -B` protections after scrubbing dynamic-loader and Python startup overrides. That bootstrap performs no network, Git, filesystem-management, or Supervisor operation. It constructs the service environment and then uses `os.execve()` to replace itself with `/app/main.py`.

The long-lived service allowlist is:

- `PATH=/usr/bin:/bin` — fixed system executable search path;
- `PYTHONNOUSERSITE=1` — defense in depth alongside Python `-s`;
- `SUPERVISOR_TOKEN` — required for authenticated Supervisor API operations;
- `TZ` — retained when supplied for operator-visible local-time behavior;
- `LANG` and `LC_ALL` — retained when supplied for locale/encoding compatibility.

All other inherited variables are absent from the service process by construction. This includes ambient proxy controls, Git overrides, Python module/search overrides, dynamic-loader controls, shell startup variables, user-home selection, and unrelated container state. Existing Python `-E -s -B` flags and the explicit pre-bootstrap dynamic-loader scrub remain as defense in depth.

## Supervisor token handling

The Supervisor token is copied directly from the bootstrap's inherited environment into the `env` mapping passed to `os.execve()`. It is never logged and is never placed in the bootstrap or service argument vector. This avoids the transient process-list exposure that would result from an `env -i SUPERVISOR_TOKEN=...` command-line launcher.

If `SUPERVISOR_TOKEN` is absent, the bootstrap does not invent it. The existing `SupervisorClient` validation continues to fail closed when Supervisor access is required.

## Bootstrap boundary

The clean allowlist begins when the bootstrap `execve()` starts the long-lived service. The bootstrap interpreter itself still begins after `/usr/bin/with-contenv bashio` and therefore cannot retroactively constrain the already-started shebang interpreter or shell. Pre-script environment trust remains a container/runtime boundary, as documented in `DYNAMIC_LOADER_ENVIRONMENT_SAFETY.md`.

The bootstrap is intentionally tiny and runs under `-E -s -B`; before it starts, `run.sh` removes the known Python code-loading and ELF loader controls. Its only job is environment construction followed by `execve()`.

## Update workflow

Environment isolation does not change update semantics. Remote changes still follow:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` is never made a Git working tree, no blind `git pull` is introduced, and the existing secret/runtime-file exclusions remain unchanged.
