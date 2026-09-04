# Python interpreter startup safety

Environment scrubbing provides a narrow, reviewable list of Python runtime controls, but the interpreter itself should also reject ambient Python environment configuration so newly introduced or previously unenumerated `PYTHON*` variables cannot become an unexpected control plane.

SyncApp now starts Python with `-E -s`:

- `-E` makes Python ignore `PYTHON*` environment variables when configuring the interpreter.
- `-s` prevents the per-user site-packages directory from being added to `sys.path`.

The explicit environment scrub and `PYTHONNOUSERSITE=1` remain in place as defense in depth and to keep the intended runtime contract visible at the entrypoint. The script still runs as `/app/main.py`, so the application-owned `/app` directory remains the normal import location; this intentionally does not use Python isolated mode `-I`, which would also enable safe-path behavior and could remove the script directory required for SyncApp's local package imports.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
