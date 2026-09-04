# Python runtime environment safety

SyncApp starts from a fixed system Python interpreter, but Python also accepts environment variables that can redirect module discovery, installation prefixes, startup behavior, debugger hooks, or bytecode-cache destinations before application-level validation begins.

The add-on entrypoint now removes inherited `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`, `PYTHONINSPECT`, `PYTHONBREAKPOINT`, and `PYTHONPYCACHEPREFIX` before launching SyncApp. It also forces `PYTHONNOUSERSITE=1` so per-user site-package locations are not added to the module search path.

These controls prevent ambient container or supervisor state from inserting additional Python code-loading locations or post-run interactive behavior into the SyncApp process. The application continues to start from the image-owned `/app/main.py` using `/usr/bin/python3` with the system-only `PATH` established by the preceding runtime executable-identity boundary.

This does not change Home Assistant configuration handling or Git transaction semantics. It only narrows the executable/import environment in which the existing safety workflow runs.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
