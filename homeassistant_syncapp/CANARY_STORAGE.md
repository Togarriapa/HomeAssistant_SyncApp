# Backup archive storage and timing canary

This probe exists to answer one narrow production-readiness question on a **disposable Home Assistant OS instance**: is downloading and structurally validating a freshly created Supervisor backup operationally affordable enough to consider as a future production safety gate?

It does **not** change SyncApp's production remote-update transaction. Production remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

The production transaction continues to rely on its pinned local rollback snapshot plus Supervisor backup identity/content/size continuity checks. Do not promote archive download into that path from repository tests alone.

## Run after PR #29 archive validation

After the ordinary canary and `canary.py --backup-archive-probe` pass on the disposable instance, run:

```sh
python3 /app/canary_storage.py
```

Defaults:

- temporary archive root: `/data`;
- hard archive download ceiling: 1024 MiB;
- required free-space reserve beyond that ceiling: 256 MiB.

For a known larger canary backup, adjust both limits explicitly, for example:

```sh
python3 /app/canary_storage.py --archive-max-mib 2048 --free-reserve-mib 512
```

`--archive-max-mib` accepts 16–8192 MiB. `--free-reserve-mib` accepts 64–8192 MiB.

## Why `/data`

PR #29 intentionally bounded the download size but used Python's default temporary directory. On an add-on this may consume the container filesystem rather than SyncApp's persistent application-data mount. This dedicated measurement probe instead places the temporary archive under `/data`, the storage domain SyncApp already uses for its isolated repository, staging, manifest, and transaction evidence.

The probe refuses a symlinked or missing data root. Before creating a Supervisor backup it requires currently available `/data` space to cover the **entire configured maximum download** plus the configured reserve. It repeats the same check after backup creation/metadata verification and immediately before download. This is conservative by design: even if the real backup is much smaller, an absent or misleading HTTP `Content-Length` must not let the canary intentionally consume the reserve while streaming up to its configured ceiling.

The reserve is also rechecked immediately after the download, before archive parsing. If concurrent storage pressure has pushed available space below the protected reserve despite a clean preflight, the probe aborts and the temporary archive is removed before further validation work. After cleanup, the reserve is checked again; remaining low-space pressure is reported as failure rather than presenting a misleading successful storage result.

If capacity is insufficient, reduce the ceiling only when the already-verified backup size makes that safe, or provision more disposable-instance storage. Do not remove the reserve simply to force the probe through.

## Evidence produced

The probe creates a fresh synchronous partial Home Assistant backup, then reuses the production `verify_homeassistant_backup()` contract before downloading anything. It therefore requires the same exact slug/name/type, Home Assistant content, database exclusion, Home Assistant version, and finite positive matching inventory/detail size evidence as the production Backup stage.

It then downloads the exact fresh slug to a random temporary directory under `/data`, using the bounded `SupervisorClient.download_backup()` implementation from PR #29, and applies the same archive identity/structure verifier. The archive is deleted when the temporary-directory scope ends, including failure paths.

Successful JSON records:

- production backup verification evidence;
- archive structural/identity evidence;
- configured maximum download and reserve;
- `/data` available bytes initially, immediately before download, after download, and after cleanup;
- signed available-space deltas during download and after cleanup;
- explicit proof that the reserve remained available after download and cleanup;
- monotonic elapsed seconds for backup creation, Supervisor metadata verification, archive download, and archive structural verification.

The available-space deltas are **observations, not equality invariants**. HAOS and other add-ons may use or free storage concurrently, so the probe does not require the post-cleanup byte count to equal the pre-download count exactly. It does, however, require available space to remain at or above the configured reserve after download and after cleanup. The temporary directory must also be removed.

## Evidence to retain for issue #4

Keep the JSON together with:

- the exact SyncApp commit;
- the redacted HAOS/Core/Supervisor fingerprint from `python3 /app/canary.py`;
- the storage location/configuration used by the disposable HAOS instance;
- whether the backup backend is local or otherwise configured;
- the backup size reported by Supervisor.

Run the probe more than once if practical. Production-gating decisions should use observed worst-case/representative backup creation and download/verification latency, not a single unusually fast run.

## Promotion rule

Do **not** make archive download a mandatory production Backup → Apply step merely because this probe succeeds once. First establish on real HAOS that:

1. backup creation plus archive download/verification latency fits the intended synchronization window;
2. `/data` has a defensible storage reserve at intended backup sizes;
3. cleanup is reliable across success and injected transport/archive failures;
4. the Supervisor storage backend used in production behaves consistently;
5. the extra read traffic does not create unacceptable I/O pressure.

If those conditions are not demonstrated, keep archive validation canary-only and retain the existing production metadata/size continuity gates.
