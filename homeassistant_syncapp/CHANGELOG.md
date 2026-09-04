# Changelog

## 0.2.0

- Add guarded remote live application behind `remote_apply_enabled: false` and `dry_run: true` defaults.
- Treat fetched remote trees as untrusted input and statically validate YAML, JSON, and Python custom-component syntax outside `/homeassistant`.
- Block ordinary remote apply when the live allowed configuration has drifted from local Git HEAD.
- Add a pre-transaction destructive-change gate for remote deletions: by default reject candidates deleting more than 25 policy-approved paths or more than 50% of the active baseline, before Supervisor backup or live mutation.
- Apply the same remote deletion budget to remote-authoritative first bootstrap using the policy-approved live configuration as its baseline; thresholds are configurable without bypassing any other validation, backup, verification, rollback, or blocked-file policy.
- Persist managed-path manifest updates durably using `fsync` on the temporary file, atomic replacement, and parent-directory `fsync`; surface durability failures so post-verification transaction evidence can be preserved and retried instead of treating bookkeeping as complete.
- Use descriptor-relative, no-follow filesystem operations for live transaction snapshotting, hashing, replacement, and deletion so a parent-path symlink swap cannot redirect the final `/homeassistant` mutation outside the directory tree that was actually opened.
- Add a staged HAOS filesystem canary: read-only `O_NOFOLLOW`/`dir_fd` validation by default, plus an explicit disposable-instance blocked-`*.tmp` create/fsync/replace/readback/unlink/directory-fsync probe with exclusive source/destination reservation and fail-closed cleanup.
- Record a redacted HAOS/Core/Supervisor runtime fingerprint in canary output and make stale `.syncapp-canary-*.tmp` evidence block the explicit write probe; successful probes prove zero matching leftovers before and after mutation.
- Make the explicit backup canary fail closed unless the newly created synchronous backup is immediately present exactly once in Supervisor inventory under the returned slug and requested canary name; restart escalation occurs only after that proof succeeds.
- Verify canary backup contents through both Supervisor inventory and `/backups/<slug>/info`: require Home Assistant content, matching identity/type, a recorded Home Assistant version, and confirmation that the database was excluded before any optional restart.
- Add an explicit disposable-HAOS backup archive probe that streams the fresh Supervisor backup download to exclusive no-follow temporary storage under bounded and, when present, `Content-Length`-verified transfer; bind `backup.json` to the exact fresh partial backup and Home Assistant/database-exclusion evidence, structurally traverse the outer and embedded Home Assistant tars without extracting configuration, reject unsafe member paths, clean partial downloads on failure, and block optional Core restart when archive proof fails.
- Bound nested Home Assistant archive parser work by rejecting any regular member declaring more than 2 GiB and any cumulative regular-file logical payload above 8 GiB before advancing through the tar stream; successful canary evidence records the bounded logical-byte total without exposing configuration contents.
- For filesystem-backed HAOS canaries, hash the complete policy-approved live configuration tree before and after the probe and fail closed on any approved path/content drift while keeping secret/runtime exclusions unchanged and hashes out of emitted evidence.
- Create live transaction temporary files with `O_EXCL|O_NOFOLLOW`, atomically replace them relative to an opened parent descriptor, fsync that descriptor after mutation, and clean temporary files when pre-replace verification fails.
- Add a persistent transaction journal and local path-level rollback snapshot before live mutation.
- Write new transaction journals as version 2 with a canonical SHA-256 integrity checksum and validate all recovery-critical fields before interpreting transaction state.
- Fail closed on corrupt recovery evidence: reject unknown states, invalid Git object IDs, duplicate/overlapping apply paths, blocked or traversal paths, malformed staged hashes, invalid backup slugs, and `existed` entries outside the apply plan.
- Cross-check every post-preparation recovery journal against the actual rollback snapshot so corruption cannot silently turn a restore operation into a deletion; corrupted journals and snapshots are preserved for inspection rather than driving automatic recovery.
- Pin every version-2 rollback snapshot file by SHA-256 and re-verify the bytes before apply and again before/during rollback copying so a damaged snapshot cannot be restored into `/homeassistant`.
- Continue accepting structurally valid version 1 journals so an upgrade does not strand recoverable transactions created by earlier experimental builds; legacy snapshots retain path-set validation but cannot gain retroactive content hashes.
- Require the transaction state itself to contain recorded Supervisor-backup evidence before `FileTransaction.apply()` is allowed to mutate live files.
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
- Add `initial_local_publish_enabled: false`; it must be explicitly enabled before a fresh instance may publish validated live Home Assistant configuration over an already-populated equal remote baseline.
- Add `initial_remote_apply_enabled: false` as a mutually exclusive remote-authoritative first-sync option.
- Require an exact equal isolated/fetched Git relationship before remote-authoritative bootstrap; non-equal populated initial states remain blocked.
- Route remote-authoritative bootstrap through the same Stage → Validate → Backup → Apply → Verify → Rollback transaction machinery as normal remote updates rather than bypassing drift protection globally.
- During remote-authoritative bootstrap, treat every policy-approved live file as the reversible transaction baseline so remote omissions are journaled deletes while `secrets.yaml`, `.storage`, databases, logs, keys/certificates, and other blocked runtime files remain outside the transaction.
- Keep both `dry_run: false` and `remote_apply_enabled: true` required before the bootstrap can mutate `/homeassistant`.
- Treat the persisted managed-path manifest as trusted safety state: malformed JSON, wrong types, blocked paths, empty paths, and traversal paths now fail closed instead of being interpreted as an empty baseline.
- Revalidate managed paths immediately before local mirroring/deletion so corrupted state cannot escape the isolated Git worktree through path traversal.
- Expose `homeassistant_repository_url` as the explicit managed Home Assistant read/write target, separate from the SyncApp source repository.
- Reject using `Togarriapa/HomeAssistant_SyncApp` itself as the managed Home Assistant repository, reject malformed multi-component GitHub targets, and reject conflicting legacy/new target options.
- Retain deprecated `repository_url` only as an upgrade compatibility alias; it is no longer presented as the default add-on option.
- Bind an existing `/data/repository` clone to its approved `origin` fetch and push destinations; a mismatched or additional effective push URL fails closed before configuration can be sent to another target.
- Recheck managed remote provenance immediately before every fetch and push so `.git/config` changes after startup cannot silently redirect synchronization.
- Bind persistent managed state to the configured branch as well as repository identity; changing `branch` on an existing managed clone fails closed instead of reusing manifest/transaction provenance against another history.
- Isolate every managed Git subprocess from inherited repository/worktree overrides and global/system Git configuration, disable repository hooks and credential helpers, and scope the GitHub authorization header to `https://github.com/` instead of applying it globally.
- Reject an existing managed clone with a missing/unreadable `origin` rather than guessing how to reconfigure persistent state.
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
