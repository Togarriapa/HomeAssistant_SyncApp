# Backup archive storage, timing, and fidelity canary

This probe exists to answer two production-readiness questions on a **disposable Home Assistant OS instance**: is downloading and validating a freshly created Supervisor backup operationally affordable, and does that archive actually contain the exact bytes of every policy-approved live Home Assistant file present while the backup is created?

It does **not** change SyncApp's production remote-update transaction. Production remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

The production transaction continues to rely on its pinned local rollback snapshot plus Supervisor backup identity/content/size continuity checks. Do not promote archive download into that path from repository tests alone.

## Run on the disposable HAOS instance

After the ordinary canary and `canary.py --backup-archive-probe` pass, run:

```sh
python3 /app/canary_storage.py
```

The operator command always uses `/homeassistant` as the live fidelity source and `/data` for temporary archive storage.

Defaults:

- temporary archive root: `/data`;
- hard archive download ceiling: 1024 MiB;
- required free-space reserve beyond that ceiling: 256 MiB.

For a known larger canary backup, adjust both storage limits explicitly, for example:

```sh
python3 /app/canary_storage.py --archive-max-mib 2048 --free-reserve-mib 512
```

`--archive-max-mib` accepts 16–8192 MiB. `--free-reserve-mib` accepts 64–8192 MiB.

## Live-byte fidelity proof

Before Supervisor backup creation, the canary enumerates the live files allowed by SyncApp's existing synchronization policy and reads each through the same descriptor-relative, no-follow `LiveFilesystem` boundary used by transactions. It records an in-memory SHA-256 map keyed by policy-approved relative path.

That map deliberately excludes the normal blocked set, including `secrets.yaml`, `.storage`, databases, logs, caches, key/certificate material, and other runtime state. The hashes and file paths are **not emitted** in canary JSON.

After the fresh backup is downloaded, archive validation requires every expected live path to appear exactly once as a regular `data/<relative>` member in the embedded Home Assistant archive and requires the archived bytes to produce the exact expected SHA-256 digest. A missing expected path, duplicate expected path, short/overlong member, or byte mismatch fails closed.

After archive verification and temporary-file cleanup, the canary re-enumerates and re-hashes the policy-approved live tree. The before/after maps must be identical. This prevents a backup made during concurrent live drift from being reported as fidelity evidence merely because the archived bytes matched one earlier snapshot.

Successful output reports only the number of expected live files, a boolean that all expected bytes were verified, and a boolean that the policy-approved live file set remained stable. It never reports configuration contents, relative paths, or hashes.

This is a canary proof of the policy-approved configuration that SyncApp itself manages. It is not a claim that blocked Home Assistant runtime material is absent from the Supervisor backup; blocked material is simply outside SyncApp's synchronization/fidelity comparison.

## Why `/data`

The archive download is placed under `/data`, the storage domain SyncApp already uses for its isolated repository, staging, manifest, and transaction evidence, rather than relying on the container's default temporary filesystem.

The probe refuses a symlinked or missing data root. Before creating a Supervisor backup it requires currently available `/data` space to cover the **entire configured maximum download** plus the configured reserve. It repeats the same check after backup creation/metadata verification and immediately before download. This is conservative by design: even if the real backup is much smaller, an absent or misleading HTTP `Content-Length` must not let the canary intentionally consume the reserve while streaming up to its configured ceiling.

The reserve is also rechecked immediately after the download, before archive parsing. If concurrent storage pressure has pushed available space below the protected reserve despite a clean preflight, the probe aborts and the temporary archive is removed before further validation work. After cleanup, the reserve is checked again; remaining low-space pressure is reported as failure rather than presenting a misleading successful storage result.

If capacity is insufficient, reduce the ceiling only when the already-verified backup size makes that safe, or provision more disposable-instance storage. Do not remove the reserve simply to force the probe through.

## Archive parser resource bounds

The transport byte ceiling is not the only resource boundary. A small compressed tar can describe a much larger logical/uncompressed payload, so archive validation applies explicit declared-size limits before advancing past regular-file headers at **both** archive layers:

- outer Supervisor archive: maximum 8 GiB for one regular member and 16 GiB cumulative regular-file logical payload;
- nested Home Assistant component archive: maximum 2 GiB for one regular member and 8 GiB cumulative regular-file logical payload;
- maximum tar members remains 100,000 per outer/inner archive;
- JSON metadata remains capped at 1 MiB.

These bounds are canary parser protections, not claims about normal Home Assistant backup size. The verifier does not extract configuration files to disk. It rejects oversized declared regular members immediately so a compressed or malformed archive cannot turn the diagnostic structural check into effectively unbounded decompression work. A normalized tar member path that collapses to an empty path is also rejected.

The outer limits are intentionally wider than the nested Home Assistant limits because the Supervisor container can carry component metadata or other material in addition to the Home Assistant payload. They are still finite so compression auto-detection at the outer layer cannot bypass the resource model.

If a legitimate disposable-HAOS backup exceeds these logical limits, record that fact in issue #4 before changing them. Do not silently raise the limits merely to make the canary pass; the real backup shape and operational cost are precisely what this canary is intended to characterize.

## Evidence produced

The probe creates a fresh synchronous partial Home Assistant backup, then reuses the production `verify_homeassistant_backup()` contract before downloading anything. It therefore requires the same exact slug/name/type, Home Assistant content, database exclusion, Home Assistant version, and finite positive matching inventory/detail size evidence as the production Backup stage.

It then downloads the exact fresh slug to a random temporary directory under `/data`, uses the bounded archive identity/structure verifier, and proves the expected live bytes described above. The archive is deleted when the temporary-directory scope ends, including failure paths.

Successful JSON records:

- production backup verification evidence;
- archive structural/identity evidence, including bounded outer and Home Assistant logical bytes;
- the count of policy-approved live files whose archived bytes were verified;
- booleans proving exact expected-byte coverage and a stable policy-approved live tree;
- configured maximum download and reserve;
- `/data` available bytes initially, immediately before download, after download, and after cleanup;
- signed available-space deltas during download and after cleanup;
- explicit proof that the reserve remained available after download and cleanup;
- monotonic elapsed seconds for backup creation, Supervisor metadata verification, archive download, and archive structural/fidelity verification.

The available-space deltas are **observations, not equality invariants**. HAOS and other add-ons may use or free storage concurrently, so the probe does not require the post-cleanup byte count to equal the pre-download count exactly. It does, however, require available space to remain at or above the configured reserve after download and after cleanup. The temporary directory must also be removed.

## Evidence to retain for issue #4

Keep the JSON together with:

- the exact SyncApp commit;
- the redacted HAOS/Core/Supervisor fingerprint from `python3 /app/canary.py`;
- the storage location/configuration used by the disposable HAOS instance;
- whether the backup backend is local or otherwise configured;
- the backup size reported by Supervisor;
- the reported outer and Home Assistant logical bytes;
- the expected-live-file count and both fidelity booleans.

Run the probe more than once if practical. Production-gating decisions should use observed worst-case/representative backup creation and download/verification latency, not a single unusually fast run.

## Promotion rule

Do **not** make archive download a mandatory production Backup → Apply step merely because this probe succeeds once. First establish on real HAOS that:

1. every policy-approved live configuration file is byte-identical in the fresh backup while the live tree remains stable;
2. backup creation plus archive download/fidelity verification latency fits the intended synchronization window;
3. `/data` has a defensible storage reserve at intended backup sizes;
4. cleanup is reliable across success and injected transport/archive failures;
5. the Supervisor storage backend used in production behaves consistently;
6. the extra read/decompression/hash traffic does not create unacceptable CPU or I/O pressure;
7. real backup logical sizes remain comfortably within the parser's declared-size bounds.

If those conditions are not demonstrated, keep archive fidelity validation canary-only and retain the existing production metadata/size continuity gates.
