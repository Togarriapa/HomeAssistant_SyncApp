# First synchronization authority

A fresh SyncApp instance has no managed-path manifest, so it has not yet established whether the live Home Assistant configuration or an already-populated Git branch is authoritative. SyncApp must not infer that choice from whichever side happens to be encountered first.

## Safe default

When the configured remote branch is populated and `/data/managed_paths.json` does not yet exist, SyncApp fails closed by default. Exactly one explicit authority mode may be enabled:

- `initial_local_publish_enabled: true`: validated live Home Assistant configuration is authoritative and may be committed/pushed to the already-populated equal Git baseline.
- `initial_remote_apply_enabled: true`: the populated remote Git commit is authoritative and may replace policy-approved live files through the guarded remote transaction.

The two options are mutually exclusive. A non-equal Git relationship is blocked for either mode because SyncApp cannot prove a single initial baseline.

## Remote-authoritative bootstrap

Remote bootstrap does not weaken the normal live-drift rule. Ordinary remote updates still require the allowed live configuration to match the local Git HEAD before any remote apply starts.

For the one-time remote-authoritative bootstrap only, live-vs-Git differences are expected. SyncApp therefore uses every currently policy-approved live file as the reversible transaction baseline. The remote commit is still treated as untrusted input and follows:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

The bootstrap requires all of the following before live mutation:

1. no managed-path manifest exists;
2. the configured remote branch is populated;
3. local isolated Git HEAD exactly equals the fetched remote commit;
4. `initial_remote_apply_enabled: true`;
5. `remote_apply_enabled: true`;
6. `dry_run: false`;
7. remote staging/static validation succeeds.

The transaction then snapshots every affected existing live file, creates a synchronous Supervisor partial Home Assistant backup, verifies staged SHA-256 pins after the backup window, atomically applies only changed policy-approved files and policy-approved deletions, runs Supervisor `/core/check`, restarts Core only after that check succeeds, verifies Core API health, re-fetches GitHub, proves the remote commit did not move, adopts the exact verified commit, writes the managed-path manifest, and removes the transaction journal.

If semantic validation, restart health, remote-commit stability, or any recoverable transaction step fails, the prior policy-approved live files are restored using the same rollback machinery as ordinary remote apply.

## Exclusions remain absolute

Remote-authoritative bootstrap never broadens the managed path policy. Files and directories such as these remain outside the transaction and are neither deleted nor overwritten from Git:

- `secrets.yaml` / `secrets.yml`;
- `.storage`, `.cloud`, backups, caches, and generated runtime directories;
- databases and SQLite files;
- logs, PID/lock/temp files, and Python bytecode;
- private keys, PEM files, certificates/PKCS containers covered by the blocked patterns;
- symlinks and unsupported Git object modes.

If a remote tree contains a blocked path, staging rejects the commit before live mutation.

## Recommended first-run procedure

Keep `dry_run: true` and `remote_apply_enabled: false` first. Enable only the intended initial authority flag and confirm logs show the expected branch/commit and successful staging. For remote authority, enable `remote_apply_enabled: true` while keeping `dry_run: true` for another observation cycle. Only on a disposable/canary Home Assistant OS instance should `dry_run` then be set to `false` to exercise the complete transaction.

Production use remains blocked on the real HAOS/Supervisor canary work tracked by issue #4.
