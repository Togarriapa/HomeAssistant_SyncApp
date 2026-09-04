# Filter-independent initial remote bootstrap

When SyncApp starts with an isolated Git repository that has no local commit but the configured remote branch is already populated, it must bind that remote commit as the local baseline before the remote configuration can enter the guarded staging/apply path.

Historically this used `git checkout -B <branch> origin/<branch>`. Checkout materializes worktree files and therefore applies smudge/process filters selected by Git attributes, including `$GIT_DIR/info/attributes`. That worktree materialization is unnecessary: remote staging reads the fetched commit tree and blob objects directly, and the live Home Assistant configuration is changed only later through the validated transaction workflow.

Initial populated-remote bootstrap now:

1. fetches and authoritatively verifies the configured remote branch as before;
2. requires the managed branch identity to remain unchanged during initialization;
3. binds HEAD and the index to `refs/remotes/origin/<branch>` with `git reset --mixed`, which does not check files out and does not run smudge filters;
4. removes stale untracked isolated-worktree state with `git clean -fdx`.

The resulting isolated worktree may contain no managed files at all. That is intentional. The remote staging path reads object evidence, validates it in the dedicated staging directory, performs the Supervisor backup, applies only after validation, verifies Home Assistant health/configuration, and only then finalizes adoption. The Git worktree is never used as a shortcut around that transaction.

Regression coverage installs a real `$GIT_DIR/info/attributes` smudge helper, proves the removed `checkout -B` operation executes it, and proves `GitRepository.ensure()` binds the same fetched commit without helper execution while leaving the worktree unmaterialized.

The required update sequence remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No blind `git pull` is introduced, `/homeassistant` remains outside Git, and secret/runtime exclusions are unchanged.
