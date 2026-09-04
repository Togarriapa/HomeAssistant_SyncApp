# Filter-independent local candidate discard

SyncApp may reject or abandon a local publication candidate after mirroring the live Home Assistant configuration into the isolated `/data` repository. Discarding that candidate must reset Git evidence without allowing repository-local attributes to execute code.

`git reset --hard HEAD` rewrites tracked worktree files and therefore applies smudge/process filters selected by Git attributes, including `$GIT_DIR/info/attributes`. That is unnecessary for SyncApp: the isolated worktree is not the live Home Assistant configuration, and the next local synchronization always rewrites approved managed files from `/homeassistant` before constructing a new candidate index.

`GitRepository.discard_worktree_changes()` therefore now:

1. resets only HEAD/index state with `git reset --mixed HEAD` when a baseline commit exists;
2. uses `git read-tree --empty` for an unborn branch instead of an index/worktree removal command;
3. removes stale untracked files with `git clean -fdx`, independent of `.gitignore` and `$GIT_DIR/info/exclude`.

Tracked candidate bytes may remain temporarily in the isolated worktree after discard. They are deliberately not treated as trusted evidence: the Git index has already been reset to the accepted baseline, and the next descriptor-confined mirror overwrites managed worktree bytes from the live Home Assistant source before the filter-independent index builder can stage anything. This avoids an attribute-selected checkout helper without weakening publication validation.

The regression suite installs a real `$GIT_DIR/info/attributes` smudge helper, proves an ordinary hard reset executes it, then verifies SyncApp discard does not execute it while still restoring the baseline index and deleting stale untracked candidate files.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No blind `git pull` is introduced, `/homeassistant` remains outside Git, and protected secret/runtime exclusions are unchanged.
