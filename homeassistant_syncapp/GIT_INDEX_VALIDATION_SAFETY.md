# Staged Git index validation binding

Local publication must validate the object that Git will actually commit, not only the isolated worktree pathnames that were mirrored from Home Assistant.

After `git add -A`, SyncApp asks Git to materialize the exact staged index as a tree with `git write-tree`, enumerates that tree with Git plumbing, and hashes each staged blob with SHA-256. Every staged entry must be a policy-approved regular blob with mode `100644` or `100755`. The staged path/hash manifest must exactly match the descriptor-validated isolated worktree candidate before Home Assistant semantic validation begins.

After `check_core_configuration()` succeeds and live-source continuity is re-proven, SyncApp obtains the staged tree manifest again. If the index changed during semantic validation, publication fails closed, isolated worktree/index changes are discarded, and no commit or push occurs.

This prevents an index-only mutation from bypassing validation merely because the visible worktree and live Home Assistant bytes remained valid.

Remote updates remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. No blind `git pull` is permitted against `/homeassistant`, and existing secret/runtime exclusions remain unchanged.
