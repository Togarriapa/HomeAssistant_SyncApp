# Git reference namespace safety

Git supports `GIT_NAMESPACE` as an environment control that makes a shared object store expose refs through a selected namespace. In SyncApp, branch refs, tracking refs, HEAD and commit identities are transaction evidence and must always refer to the managed repository's primary namespace.

Before constructing the synchronization engine, SyncApp removes inherited `GIT_NAMESPACE`. This prevents ambient add-on/container state from changing which branch/ref namespace Git commands observe or update.

This complements the existing descriptor-pinned repository metadata, authoritative remote-ref verification, and disabled replacement-object behavior. It does not alter legitimate branch configuration inside the managed primary namespace.

The live update contract remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. `/homeassistant` remains outside Git, no blind `git pull` is used, and secret/runtime exclusions are unchanged.
