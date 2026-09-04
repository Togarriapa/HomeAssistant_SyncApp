# Python process environment allowlist

SyncApp does not let the long-lived Python service inherit the add-on container environment wholesale. Immediately before Python starts, `run.sh` uses `/usr/bin/env -i` to construct a new environment containing only the runtime inputs the application deliberately needs.

The allowlist is:

- `PATH=/usr/bin:/bin` — fixed system executable search path;
- `PYTHONNOUSERSITE=1` — defense in depth alongside Python `-s`;
- `SUPERVISOR_TOKEN` — required for authenticated Supervisor API operations;
- `TZ` — retained for operator-visible local-time behavior;
- `LANG` and `LC_ALL` — retained for locale/encoding compatibility.

All other inherited variables are absent from the Python process by construction. This includes ambient proxy controls, Git overrides, Python module/search overrides, dynamic-loader controls, shell startup variables, user-home selection, and unrelated container state. Existing Python `-E -s -B` flags and the explicit pre-exec dynamic-loader scrub remain as defense in depth.

The image build verifies that `/usr/bin/env`, `/usr/bin/python3`, and `/usr/bin/git` are present at their fixed paths.

## Supervisor token

The Supervisor token is intentionally copied without logging it. If it is unavailable, the allowlist passes an empty value and the existing `SupervisorClient` validation fails closed when Supervisor access is required.

## Bootstrap boundary

This allowlist starts at the Python `exec`. It cannot retroactively constrain `/usr/bin/with-contenv bashio` or the shell that has already interpreted `run.sh`. Pre-script environment trust therefore remains a container/runtime boundary, as documented in `DYNAMIC_LOADER_ENVIRONMENT_SAFETY.md`.

## Update workflow

Environment isolation does not change update semantics. Remote changes still follow:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` is never made a Git working tree, no blind `git pull` is introduced, and the existing secret/runtime-file exclusions remain unchanged.
