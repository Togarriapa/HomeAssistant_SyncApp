# Git pathspec safety

SyncApp supplies repository paths programmatically. Those paths are already policy-validated relative paths and must identify exactly the intended managed file; they are not user-authored Git patterns.

Git supports ambient pathspec controls that can globally enable globbing, disable globbing, or make matching case-insensitive. In a long-running service, inherited values for those controls must not change the meaning of a path supplied by SyncApp.

SyncApp therefore removes inherited `GIT_GLOB_PATHSPECS`, `GIT_NOGLOB_PATHSPECS`, and `GIT_ICASE_PATHSPECS`, then forces `GIT_LITERAL_PATHSPECS=1` before constructing the synchronization engine. Git path arguments supplied by the application are consequently interpreted as literal path names rather than glob or pathspec-magic expressions.

The current Git command surface does not intentionally depend on glob or case-insensitive pathspec matching. Managed index construction already enumerates approved files itself, hashes exact descriptor-pinned bytes with filters disabled, and gives `git update-index` exact relative paths.

This is an interpretation hardening boundary only. It does not broaden which Home Assistant files are managed, bypass policy checks, or alter the remote-update transaction.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
