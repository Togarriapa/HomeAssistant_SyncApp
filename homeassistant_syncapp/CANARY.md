# Home Assistant OS canary

SyncApp's repository tests cannot prove the behavior of the real Home Assistant OS `/homeassistant` mount or Supervisor. Run these probes only on a disposable/canary Home Assistant OS installation before enabling automatic remote apply on an important instance.

## 1. Non-mutating Supervisor probe

```sh
python3 /app/canary.py
```

This checks Core info, the Supervisor Core API proxy, and Supervisor `/core/check`. It does not modify Home Assistant configuration files.

## 2. Read-only live-filesystem probe

```sh
python3 /app/canary.py --filesystem
```

This opens `/homeassistant` with `O_DIRECTORY|O_NOFOLLOW`, exercises descriptor-relative open/stat on the actual mount, and reads `configuration.yaml` through the same no-follow `LiveFilesystem` boundary used by transactions. It reports capability/proof booleans, not configuration contents or hashes.

A different policy-approved regular file can be selected explicitly:

```sh
python3 /app/canary.py --filesystem --filesystem-path packages/example.yaml
```

Blocked paths such as `secrets.yaml`, traversal paths, and symlinked roots/parents remain rejected by the normal policy and no-follow checks.

## 3. Explicit filesystem mutation primitive probe

Only on the disposable canary:

```sh
python3 /app/canary.py --filesystem --filesystem-write-probe
```

This does **not** edit a Home Assistant configuration file. It creates a random `.syncapp-canary-*.tmp` file directly under `/homeassistant`, fsyncs it, descriptor-relatively renames it to another random blocked `*.tmp` name, verifies the bytes through `O_NOFOLLOW`, unlinks it with `dir_fd`, and fsyncs the directory. `*.tmp` is already blocked by SyncApp's synchronization policy.

The probe attempts cleanup on every exit path. If cleanup itself fails, the command fails loudly and identifies the `.syncapp-canary-*.tmp` pattern for operator inspection. Do not enable remote apply until the reason is understood and any residual probe file is removed.

## 4. Supervisor backup and restart probes

After the read-only checks pass:

```sh
python3 /app/canary.py --filesystem --backup
python3 /app/canary.py --filesystem --backup --restart --timeout 120
```

The backup call creates a synchronous partial Home Assistant backup. The restart variant explicitly restarts Core and waits for the API to become healthy.

## 5. Full transaction canary

Only after all preceding levels pass should the disposable instance test an actual harmless remote commit through SyncApp's complete workflow:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

Keep both `dry_run: true` and `remote_apply_enabled: false` while establishing the initial canary evidence. Enable live remote mutation only on the disposable instance and only for the issue #4 acceptance matrix.

The canary helper is not a substitute for that full transaction exercise. In particular, the temporary-file write probe proves descriptor-relative replace/unlink/fsync support but does not prove Supervisor backup semantics, `/core/check` behavior after a recoverable update, restart health transitions, transaction recovery after process/power interruption, or exact Git adoption.
