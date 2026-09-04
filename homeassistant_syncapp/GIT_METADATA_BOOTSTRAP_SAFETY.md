# Git metadata bootstrap safety

A newly created managed repository previously had one residual identity gap: the repository root was descriptor-pinned, but `.git` did not exist until `git init` created it. That meant the metadata directory could not be bound to the `GitRepository` identity before the first Git subprocess.

Bootstrap now creates `.git` itself, descriptor-relative to the already pinned repository root, with restrictive permissions. Creation is exclusive: if `.git` appears concurrently, bootstrap fails closed and preserves that unexpected state rather than treating it as the directory SyncApp intended to create.

Immediately after creation, SyncApp opens `.git` with `O_DIRECTORY | O_NOFOLLOW`, binds its device/inode identity, and proves the root directory entry still identifies that exact object. Only then is `git init` launched. The initialization subprocess receives descriptor-backed `GIT_DIR` and `GIT_WORK_TREE` values and inherits both descriptors, so a rename/replacement after binding cannot redirect initialization into replacement metadata. Post-command identity checks still reject any such substitution.

If initialization fails, the partially initialized metadata is intentionally preserved for inspection; SyncApp does not recursively erase or silently recreate control state on retry.

This completes the root/metadata identity chain for first-run repository initialization without changing live Home Assistant semantics. `/homeassistant` remains outside Git, remote updates remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**, and secret/runtime exclusions remain unchanged.
