# Python bytecode write safety

SyncApp application code is supplied by the add-on image and should remain read-only in intent while the service is running. Python normally may create or update `__pycache__` bytecode files while importing modules, introducing unnecessary runtime writes beneath the image-owned application tree.

The add-on now starts Python with `-B` in addition to the existing `-E -s` startup controls. `-B` prevents Python from writing `.pyc` bytecode cache files during imports. This reduces mutable runtime state and avoids stale generated import artifacts persisting across process restarts within the same container.

The source modules continue to be imported normally from `/app`; only cache writes are disabled. This does not affect Home Assistant configuration files, Git transaction evidence, staging, backups, apply, verification, or rollback behavior.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
