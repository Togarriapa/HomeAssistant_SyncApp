# Git replacement-object safety

Git replacement refs under `refs/replace/` can transparently substitute one object for another for many Git commands. That is incompatible with SyncApp's integrity model: a commit, tree, or blob object ID used as transaction evidence must resolve to the object actually stored under that ID, not to a repository-local substitute.

Every SyncApp Git subprocess therefore runs with `GIT_NO_REPLACE_OBJECTS=1`. Any inherited value is removed before the fixed value is installed, so ambient runtime state cannot re-enable replacement-object resolution.

This matters for operations such as `cat-file`, tree inspection, revision resolution, reset/checkout behavior, and ancestry checks. Git's own documentation notes that replacement refs are used by default by most commands and that `GIT_NO_REPLACE_OBJECTS` disables that substitution.

Regression coverage creates two real blob objects, installs a `refs/replace/` mapping that makes ordinary Git return attacker-selected bytes for the trusted object ID, and then proves `GitRepository.read_blob()` still returns the original object bytes.

This hardening composes with descriptor-pinned repository and `.git` identities, the exact configured transport authority, HTTPS-only production protocol policy, staged-tree verification, and transaction evidence checks. It does not delete or mutate a pre-existing replacement ref; it makes SyncApp ignore it, preserving unknown repository state while failing to let that state alter object identity semantics.

The live update sequence remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No blind `git pull` is introduced, `/homeassistant` remains outside the Git worktree, and protected secret/runtime exclusions are unchanged.
