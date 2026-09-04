# Optional Git operation safety

SyncApp performs explicit repository mutations only at deliberate transaction and publication steps. Read-oriented Git commands must not gain unrelated bookkeeping side effects merely because Git considers an operation optional.

Git documents `GIT_OPTIONAL_LOCKS=0` as disabling optional operations that require locks, such as an incidental index refresh during `git status`. SyncApp now forces that value before constructing the synchronization engine, overriding inherited attempts to enable optional side effects.

Mandatory locks required by explicit repository updates remain available. This setting does not disable intentional index/ref writes, controlled Fetch, commit creation, or publication; it only suppresses optional Git side operations that are not necessary to the requested command.

This complements descriptor-pinned repository metadata, filter-independent index construction, disabled lazy object fetching, and the existing transaction integrity checks.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
