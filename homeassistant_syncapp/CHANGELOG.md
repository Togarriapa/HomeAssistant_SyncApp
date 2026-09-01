# Changelog

## 0.1.0

- Bootstrap the Home Assistant app structure.
- Add safe file filtering for local configuration capture.
- Add authenticated Git operations without embedding the token in the remote URL.
- Add local-to-GitHub synchronization with dry-run enabled by default.
- Detect remote divergence and refuse unsafe local pushes or applies.
- Stage remote Git trees outside the live Home Assistant configuration and reject blocked paths, symlinks, unsupported modes, oversized content, and malformed YAML/JSON.
- Add guarded remote live application behind `remote_apply_enabled: false` and `dry_run: true` defaults.
- Block remote apply when the live allowed configuration has drifted from local Git HEAD.
- Add a persistent transaction journal and local rollback snapshot before live mutation.
- Require a synchronous Supervisor partial backup before applying files.
- Run the Supervisor Core configuration check before restart and verify the Core API after restart.
- Restore the previous files and Core state when validation or health verification fails.
- Preserve unresolved rollback journals when recovery health cannot be proven.
- Recover interrupted transactions before starting new Git synchronization.
- Re-fetch the remote branch before adopting a verified commit as the local baseline.
- Add failure-injection tests for backup, semantic-check, post-restart health, rollback-health, crash recovery, live drift, and symlink defenses.
