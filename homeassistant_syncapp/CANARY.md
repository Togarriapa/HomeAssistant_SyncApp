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

When `--filesystem` (or the explicit filesystem write probe) is active, the canary also snapshots the complete **policy-approved** live configuration tree before the Supervisor/filesystem escalation and hashes it again afterward. Success requires the same approved path set and identical contents. Output reports only the number of approved files and boolean proof fields; file hashes and configuration contents are never emitted. Secret/runtime exclusions remain authoritative, so normal changes to blocked runtime state such as logs, `.storage`, databases, and canary `*.tmp` files do not create false configuration-drift evidence.

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

The backup call creates a synchronous partial Home Assistant backup and invokes the **same production backup verifier used by remote transactions**. Success requires exactly one inventory entry with the returned slug, exact requested canary name, `type: partial`, `content.homeassistant: true`, and a finite positive backup size. The canary then reads `/backups/<slug>/info` and requires the same slug/name/type, a non-empty Home Assistant version, `homeassistant_exclude_database: true`, another finite positive size, and numeric agreement between inventory and detail size evidence.

Successful JSON `backup` evidence therefore includes `inventory_verified: true`, `detail_verified: true`, `homeassistant_content_verified: true`, `homeassistant_database_excluded: true`, `backup_size_verified: true`, the normalized positive backup size, the backed-up Home Assistant version, and selected non-sensitive inventory metadata. The canary never restores, deletes, or prunes a backup as part of this proof.

The restart variant completes every backup proof **before** explicitly restarting Core and waiting for the API to become healthy. Restart without `--backup` is refused. Missing/duplicate inventory evidence, missing Home Assistant content, identity/type disagreement, absent Home Assistant version, invalid/zero/disagreeing size evidence, or failure to confirm database exclusion all stop the canary before restart.

Because these commands include `--filesystem`, they also require `live_configuration_invariance.path_set_unchanged: true` and `live_configuration_invariance.content_unchanged: true` after backup/restart. This automates the issue #4 requirement that canary activity must not alter policy-approved Home Assistant configuration. If another actor edits allowed configuration during the run, the proof also fails closed rather than incorrectly attributing a clean result.

## 5. Explicit downloaded-backup archive probe

Only on the disposable canary, after the ordinary backup proof succeeds:

```sh
python3 /app/canary.py --filesystem --backup --backup-archive-probe
```

This is deliberately an **opt-in canary escalation**, not a production Backup → Apply prerequisite. The helper downloads the fresh canary backup through Supervisor `GET /backups/<slug>/download` into a newly created temporary file, with no-follow/exclusive creation and a hard streaming byte ceiling. The default ceiling is 1024 MiB and can be changed for a known larger canary backup, up to 8192 MiB:

```sh
python3 /app/canary.py --filesystem --backup --backup-archive-probe --backup-archive-max-mib 2048
```

When the HTTP response provides `Content-Length`, the downloader rejects malformed or non-positive values, refuses a declared length above the configured ceiling before consuming the body, and requires the final byte count to match. The streaming byte ceiling remains authoritative even when `Content-Length` is absent or inaccurate. A failed, truncated, oversized, empty, HTTP-error, or transport-error download removes its partial temporary file.

The downloaded archive is never extracted into the filesystem. SyncApp only parses tar headers, reads tightly bounded metadata JSON, and streams the embedded Home Assistant component tar. Success requires:

- the complete outer tar to be structurally readable;
- exactly one bounded, non-empty, valid-JSON `backup.json`;
- `backup.json` to identify the exact fresh canary slug and requested name;
- `backup.json` to report `type: partial`;
- `backup.json` to describe Home Assistant content, confirm database exclusion, and report the same Home Assistant version proven by the Supervisor API;
- exactly one non-empty `homeassistant.tar` or `homeassistant.tar.gz`;
- the embedded Home Assistant tar to be structurally readable;
- exactly one bounded, non-empty, valid-JSON `homeassistant.json` inside that component archive;
- at least one regular file under the component `data/` tree;
- no absolute, traversal, backslash-based, or otherwise unsafe archive member paths;
- the temporary downloaded tar to be removed when the probe finishes.

Metadata members are capped at 1 MiB and each tar traversal is capped at 100,000 members. The streaming client refuses to overwrite an existing destination and fails rather than consuming unlimited temporary storage. The JSON evidence reports counts and proof booleans only; it does not expose configuration filenames, file contents, hashes, backup passwords, or extracted data.

To combine archive validation with the restart test, use:

```sh
python3 /app/canary.py --filesystem --backup --backup-archive-probe --restart --timeout 120
```

Archive download, identity binding, and structural verification complete **before** Core restart. Any transport-length mismatch, mismatched backup identity/type/database-exclusion/version, malformed/truncated outer tar, or malformed Home Assistant component tar therefore blocks the optional restart. This check is useful evidence for issue #4 because successful Supervisor metadata alone does not prove that the actual downloadable artifact is the same backup or can be traversed as a backup archive.

Do not automatically promote this archive read into the production remote-apply transaction until disposable-HAOS evidence establishes realistic download latency, temporary-storage consumption, and behavior for the intended backup sizes/storage locations. The production transaction continues to rely on the pinned local rollback snapshot plus Supervisor metadata/size continuity gates.

## 6. Full transaction canary

Only after all preceding levels pass should the disposable instance test an actual harmless remote commit through SyncApp's complete workflow:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

Keep both `dry_run: true` and `remote_apply_enabled: false` while establishing the initial canary evidence. Enable live remote mutation only on the disposable instance and only for the issue #4 acceptance matrix.

The canary helper is not a substitute for that full transaction exercise. The temporary-file write probe proves descriptor-relative replace/unlink/fsync support, the backup metadata probe proves Supervisor recorded the requested Home Assistant backup contents and size evidence, the archive probe binds the fresh downloaded artifact to that backup and proves its transport, outer tar, and embedded Home Assistant archive are structurally coherent, and the invariance proof shows the canary itself did not alter policy-approved live configuration. These still do not prove `/core/check` behavior after a recoverable remote update, transaction recovery after process/power interruption, restoreability on another machine, or exact Git adoption.
