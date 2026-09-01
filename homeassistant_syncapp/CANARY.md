# Home Assistant OS canary

SyncApp's repository tests cannot prove the behavior of the real Home Assistant OS `/homeassistant` mount or Supervisor. Run these probes only on a disposable/canary Home Assistant OS installation before enabling automatic remote apply on an important instance.

## Evidence handling

Every canary invocation records a deliberately small `environment` object before the health/configuration checks. It contains only the installed Core version/architecture/machine/image, Supervisor version/architecture, and host operating-system/kernel/agent/deployment/virtualization fields needed to make issue #4 results reproducible. The helper intentionally does **not** include hostnames, network addresses, disk inventory, the Supervisor token, or the `version_latest` advisory fields.

Save the JSON output from each level together with the exact SyncApp commit being tested. Do not treat output from one HAOS/Core/Supervisor version combination as proof for a materially different runtime without rerunning the canary.

## 1. Non-mutating Supervisor probe

```sh
python3 /app/canary.py
```

This records the redacted runtime fingerprint, checks the Supervisor Core API proxy, and runs Supervisor `/core/check`. It does not modify Home Assistant configuration files.

## 2. Read-only live-filesystem probe

```sh
python3 /app/canary.py --filesystem
```

This opens `/homeassistant` with `O_DIRECTORY|O_NOFOLLOW`, exercises descriptor-relative open/stat on the actual mount, and reads `configuration.yaml` through the same no-follow `LiveFilesystem` boundary used by transactions. It reports capability/proof booleans, not configuration contents or hashes. The command fails if the selected probe path is missing, blocked, a symlink, or not a regular file; a successful result therefore proves that the production read path actually ran.

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

This does **not** edit a Home Assistant configuration file. Before creating anything, it descriptor-relatively scans the opened live root for prior `.syncapp-canary-*.tmp` evidence. If any matching file exists, the write probe refuses to run and leaves that evidence untouched for operator inspection.

With a clean preflight, the probe creates two random `.syncapp-canary-*.tmp` files directly under `/homeassistant` using `O_EXCL|O_NOFOLLOW`, so both source and destination names are proven to belong to that canary invocation before replacement. It fsyncs the source, descriptor-relatively replaces the reserved destination with the source, verifies the bytes through `O_NOFOLLOW`, unlinks the destination with `dir_fd`, and fsyncs the directory. `*.tmp` is already blocked by SyncApp's synchronization policy.

The probe attempts cleanup on every exit path, including replacement failure, then scans for matching leftovers again before reporting success. A successful result contains `stale_probe_files_before: 0` and `stale_probe_files_after: 0`. If cleanup itself fails or matching evidence remains, the command fails loudly. Do not enable remote apply until the reason is understood and residual probe evidence is resolved. A random-name collision also fails closed; the canary never intentionally replaces an unowned path.

## 4. Supervisor backup and restart probes

After the read-only checks pass:

```sh
python3 /app/canary.py --filesystem --backup
python3 /app/canary.py --filesystem --backup --restart --timeout 120
```

The backup call creates a synchronous partial Home Assistant backup and then immediately reads Supervisor backup inventory. Success requires exactly one inventory entry with the returned slug and the exact canary backup name that was requested. The JSON `backup` evidence includes the slug, `inventory_verified: true`, `name_matches_request: true`, and selected non-sensitive inventory metadata when Supervisor supplies it. The canary never deletes a backup as part of this proof.

The restart variant performs the same backup creation/inventory proof **before** explicitly restarting Core and waiting for the API to become healthy. If the newly created slug is absent, duplicated, or associated with a different name, the canary fails before issuing the restart so a questionable backup cannot be treated as established recovery evidence.

## 5. Full transaction canary

Only after all preceding levels pass should the disposable instance test an actual harmless remote commit through SyncApp's complete workflow:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

Keep both `dry_run: true` and `remote_apply_enabled: false` while establishing the initial canary evidence. Enable live remote mutation only on the disposable instance and only for the issue #4 acceptance matrix.

The canary helper is not a substitute for that full transaction exercise. In particular, the temporary-file write probe proves descriptor-relative replace/unlink/fsync support, while the backup probe proves creation plus inventory visibility. Neither proves `/core/check` behavior after a recoverable update, restart health transitions, transaction recovery after process/power interruption, or exact Git adoption.
