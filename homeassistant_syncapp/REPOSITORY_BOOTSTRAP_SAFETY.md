# Managed repository bootstrap safety

The persistent Git checkout under `/data` is control state, not disposable scratch space. First-run bootstrap must therefore never recursively erase an unexpected pathname merely because `.git` is absent.

SyncApp now requires the configured repository root to be either absent or an empty real directory. A symlinked/non-directory root, a non-empty unmanaged directory, or non-directory/symlinked `.git` metadata fails closed and is preserved for inspection. Unknown state is not "repaired" by recursive deletion.

For a safe empty root, SyncApp initializes Git locally, pins the configured branch with a symbolic `HEAD`, records the configured repository URL as `origin`, and then enters the same provenance-checked, configured-URL Fetch path used by established repositories. This avoids an initial broad `git clone` plus destructive pre-clone cleanup and ensures only the managed branch is fetched into local tracking state.

If the configured branch exists remotely, bootstrap checks it out only after the pinned Fetch phase has authoritatively populated `refs/remotes/origin/<branch>`. If the remote is empty, the managed branch remains unborn and the repository relationship remains `empty` until a validated local publication creates the first commit.

This changes only isolated `/data` Git control state. `/homeassistant` remains outside Git and remote application still follows **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. No blind `git pull` is introduced and secret/runtime exclusions remain unchanged.
