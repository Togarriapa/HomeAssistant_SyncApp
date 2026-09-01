# Changelog

## 0.2.0

- Add guarded remote live application behind `remote_apply_enabled: false` and `dry_run: true` defaults.
- Treat fetched remote trees as untrusted input and statically validate YAML, JSON, and Python custom-component syntax outside `/homeassistant`.
- Block ordinary remote apply when the live allowed configuration has drifted from local Git HEAD.
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
- After an exact verified commit has been adopted in Git, preserve live files and the verified journal if manifest/final cleanup bookkeeping fails; retry proof-based finalization on the next cycle instead of rolling live files back behind the adopted Git baseline.
- Treat a residual `completed` journal as post-verification bookkeeping state: finalize only when the adopted Git commit and live managed files can still be proven to match, otherwise preserve evidence and block automatic rollback.
- Add bounded retention for old unprotected SyncApp-created pre-apply backups; protected and unrelated backups are never selected for deletion.
- Validate local-to-GitHub candidates with the same static size/syntax rules and live Supervisor `/core/check` before creating commits.
- Refuse local commits when the existing Git index tracks any blocked secret/runtime path.
- Discard rejected and dry-run local candidates from the isolated Git worktree so staged state cannot leak into later cycles.
- Fail closed on first synchronization when the configured remote branch is already populated instead of silently choosing local or remote authority.
- Add `initial_local_publish_enabled: false`; it must be explicitly enabled before a fresh instance may publish validated live configuration over an already-populated equal remote baseline.
- Add `initial_remote_apply_enabled: false` as a mutually exclusive remote-authoritative first-sync option.
- Require an exact equal isolated/fetched Git relationship before remote-authoritative bootstrap; non-equal populated first-sync states remain blocked.
- Route remote-authoritative bootstrap through the same Stage → Validate → Backup → Apply → Verify → Rollback transaction machinery as normal remote updates rather than bypassing drift protection globally.
- During remote-authoritative bootstrap, treat every policy-approved live file as the reversible baseline so remote omissions are journaled deletes while `secrets.yaml`, `.storage`, databases, logs, keys/certificates, and other blocked runtime files remain outside the transaction.
- Keep both `dry_run: false` and `remote_apply_enabled: true` required before the bootstrap can mutate `/homeassistant`.
- Treat the persisted managed-path manifest as trusted safety state: malformed JSON, wrong types, blocked paths, empty paths, and traversal paths now fail closed instead of being interpreted as an empty baseline.
- Revalidate managed paths immediately before local mirroring/deletion so corrupted state cannot escape the isolated Git worktree through path traversal.
- Expose `homeassistant_repository_url` as the explicit managed Home Assistant read/write target, separate from the SyncApp source repository.
- Reject using `Togarriapa/HomeAssistant_SyncApp` itself as the managed Home Assistant repository, reject malformed multi-component GitHub targets, and reject conflicting legacy/new target options.
- Retain deprecated `repository_url` only as an upgrade compatibility alias; it is no longer presented as the default add-on option.
- Reject symlinked live targets and symlinked live configuration roots.
- Add unit, failure-injection, Supervisor-contract, apply-plan, local/remote end-to-end Git integration, and static type-check coverage.
- Build the Docker image using the version declared in app metadata.

## 0.1.0

- Bootstrap the Home Assistant app structure.
- Add safe file filtering for local configuration capture.
- Add authenticated Git operations without embedding the token in the remote URL.
- Add local-to-GitHub synchronization with dry-run enabled by default.
- Detect remote divergence and refuse unsafe local pushes.
- Stage remote Git trees outside the live Home Assistant configuration and reject blocked paths, symlinks, unsupported modes, oversized content, and malformed YAML/JSON.
