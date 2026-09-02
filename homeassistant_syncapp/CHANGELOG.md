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
