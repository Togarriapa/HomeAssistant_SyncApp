# Changelog

## 0.2.0

- Add guarded remote live application behind `remote_apply_enabled: false` and `dry_run: true` defaults.
- Treat fetched remote trees as untrusted input and statically validate YAML, JSON, and Python custom-component syntax outside `/homeassistant`.
- Block remote apply when the live allowed configuration has drifted from local Git HEAD.
- Add a persistent transaction journal and local path-level rollback snapshot before live mutation.
- Require a synchronous Supervisor partial Home Assistant backup before applying files.
- Run the Supervisor Core configuration check after recoverable application and before restart.
- Verify the Home Assistant Core API after restart through the Supervisor proxy.
- Restore previous files and Core state when semantic validation, restart health, or final Git-baseline adoption fails.
- Preserve unresolved rollback journals when recovery health cannot be proven.
- Recover interrupted transactions before starting new Git synchronization, while avoiding unnecessary Core restarts for pre-apply transaction states.
- Re-fetch the remote branch before adopting a verified commit so a branch move during backup/restart causes rollback.
- Pin staged transaction writes with SHA-256 so staged bytes cannot change during a long Supervisor backup window.
- Fail closed when a verified/adopted transaction has ambiguous live drift before crash-recovery bookkeeping completes.
- Add bounded retention for old unprotected SyncApp-created pre-apply backups; protected and unrelated backups are never selected for deletion.
- Validate local-to-GitHub candidates with the same static size/syntax rules and live Supervisor `/core/check` before creating commits.
- Refuse local commits when the existing Git index tracks any blocked secret/runtime path.
- Discard rejected and dry-run local candidates from the isolated Git worktree so staged state cannot leak into later cycles.
- Reject symlinked live targets and symlinked live configuration roots.
- Add unit, failure-injection, Supervisor-contract, apply-plan, local end-to-end Git integration, and static type-check coverage.
- Build the Docker image using the version declared in app metadata.

## 0.1.0

- Bootstrap the Home Assistant app structure.
- Add safe file filtering for local configuration capture.
- Add authenticated Git operations without embedding the token in the remote URL.
- Add local-to-GitHub synchronization with dry-run enabled by default.
- Detect remote divergence and refuse unsafe local pushes.
- Stage remote Git trees outside the live Home Assistant configuration and reject blocked paths, symlinks, unsupported modes, oversized content, and malformed YAML/JSON.
