# Git lazy-fetch evidence safety

SyncApp validates fetched commits, trees, and blobs as local transaction evidence before any live Home Assistant mutation. Missing object evidence must therefore fail locally rather than cause an implicit network request from an object-inspection command.

Git supports partial/promisor repositories where commands can lazily fetch a missing object from a promisor remote. `GIT_NO_LAZY_FETCH=1` disables that behavior. SyncApp now forces that value before constructing the synchronization engine, overriding inherited attempts to re-enable lazy fetching.

This keeps network activity explicit at the **Fetch** boundary. Later staging and verification operations consume the objects already obtained by the controlled, configured-URL Fetch path; they do not gain a second hidden route to acquire missing evidence.

The setting does not remove SyncApp's explicit Fetch operation, change remote provenance checks, or rewrite repository state. A missing object encountered after Fetch is treated as incomplete local evidence and the operation fails closed.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
