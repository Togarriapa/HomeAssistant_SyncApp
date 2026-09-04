# Git executable identity safety

SyncApp treats Git as part of its transaction-evidence and transport control plane. The executable used to interpret refs, commits, trees, blobs, configuration, and remote operations therefore must not be selected by ambient `PATH` state.

Production Git subprocesses use the absolute executable `/usr/bin/git` rather than the bare command name `git`. A writable or attacker-controlled directory placed earlier in `PATH` can no longer substitute a different top-level Git program for SyncApp operations.

The container build installs Git explicitly and verifies that `/usr/bin/git` exists and is executable. CI regression coverage also places a hostile executable named `git` in the only inherited `PATH` entry and proves that both text and byte-oriented `GitRepository` subprocess paths still execute the pinned system Git binary without invoking the attacker program.

This boundary composes with the existing scrubbing of `GIT_EXEC_PATH`, Git configuration injection controls, disabled hooks and executable helpers, HTTPS-only production transport policy, descriptor-pinned repository metadata, and filter-independent Git index construction.

Pinning the top-level Git executable does not by itself claim that every helper program Git may resolve internally has a pinned identity. Helper search-path confinement remains a separate boundary and should be hardened independently where compatibility can be demonstrated.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
