# Managed Git repository format safety

SyncApp treats the isolated repository under `/data` as control-state and transaction evidence, not as the live Home Assistant configuration tree. Its bootstrap therefore must not inherit repository-format choices from ambient container state.

Before `SyncEngine` constructs the managed repository, SyncApp now pins:

- `GIT_DEFAULT_HASH=sha1`
- `GIT_DEFAULT_REF_FORMAT=files`

Git documents these environment variables as selecting the default object hash algorithm and reference backend for newly initialized repositories. Without an explicit SyncApp policy, inherited values could cause first-run `git init` to create a repository whose object/ref representation differs from the format expected by the existing safety, compatibility, and remote-publication model.

This is deliberately a bootstrap-format boundary only. It does not rewrite an existing repository, silently migrate metadata, or relax any provenance checks. Existing repositories continue to be validated and used in place; ambiguous or incompatible state must fail closed rather than be recreated destructively.

The live update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
