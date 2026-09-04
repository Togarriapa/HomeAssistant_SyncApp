# Git reference backend environment safety

SyncApp treats branch, tracking-ref, and HEAD identities in the isolated `/data` repository as control-state and transaction evidence. Ambient container state must not be able to replace the reference backend used to interpret that evidence.

Git supports `GIT_REFERENCE_BACKEND`, which selects a reference backend and backend-specific URI and takes precedence over repository configuration. SyncApp therefore removes inherited `GIT_REFERENCE_BACKEND` before constructing the synchronization engine.

This protection composes with two adjacent boundaries:

- inherited `GIT_NAMESPACE` is removed so managed refs stay in the repository's primary namespace;
- first-run repository creation pins the expected SHA-1 object format and files reference backend rather than inheriting bootstrap-format selectors.

The reference-backend scrub does not rewrite, migrate, or destructively recreate an existing repository. Existing managed repository metadata remains subject to the descriptor-pinned repository and `.git` identity checks and the existing fail-closed provenance rules.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
