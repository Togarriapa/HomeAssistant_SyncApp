# Filter-independent verified remote adoption

After a remote commit has passed **Fetch → Stage → Validate → Backup → Apply → Verify**, SyncApp must advance the isolated Git baseline to that exact commit. This bookkeeping step must not create a new execution path from repository-local Git attributes.

`git reset --hard` materializes worktree files and therefore applies smudge/process filters selected by Git attributes, including `$GIT_DIR/info/attributes`. A malicious metadata-local attribute plus `filter.<name>.smudge` could execute an external helper after the live Home Assistant transaction had already verified successfully.

Verified remote adoption no longer uses a hard reset. `GitRepository.adopt_remote()` now:

1. requires `refs/remotes/origin/<managed-branch>` to still identify the exact verified commit;
2. advances HEAD and the index with `git reset --mixed <verified-commit>`, which does not check files out and therefore does not run smudge filters;
3. removes stale untracked files from the isolated `/data` worktree with `git clean -fdx` so abandoned local candidates cannot survive through ignore rules.

The isolated worktree is intentionally allowed to remain byte-stale immediately after adoption. It is not Home Assistant's live configuration and it is not publication evidence. On the next synchronization cycle the existing descriptor-confined local mirror rewrites it from `/homeassistant` before the filter-independent index builder constructs any candidate tree. Because the verified live configuration already corresponds to the adopted remote commit, that mirror should converge without producing a publication change.

This ordering is safety-oriented: no attribute-selected helper executes as part of the post-verification Git bookkeeping, the exact remote commit remains the authoritative baseline, and stale untracked candidate files are removed without relying on `.gitignore` or `$GIT_DIR/info/exclude`.

The remote-update contract remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No blind `git pull` is introduced, `/homeassistant` remains outside Git, and the secret/runtime exclusion policy is unchanged.
