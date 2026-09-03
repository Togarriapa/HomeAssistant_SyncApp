# Descriptor-pinned staging validation

SyncApp treats the materialized staging tree as untrusted mutable evidence until its exact path set and bytes have passed static validation. Validation must not regain trust by following mutable pathnames.

## Boundary

`validate_configuration_directory()` opens the staging root with `O_DIRECTORY | O_NOFOLLOW` through `PinnedReadRoot`. When an earlier stage already captured the root device/inode, validation requires the opened descriptor to match that identity.

Allowed files are enumerated relative to already-open directory descriptors. Nested directories are opened with `O_NOFOLLOW`, their directory-entry identity is compared with the opened descriptor, and the parent entry is checked again after recursion. Policy-blocked runtime directories remain skipped exactly as before.

Each allowed leaf is opened relative to its pinned parent with `O_NOFOLLOW`. The exact bytes read from that descriptor are size-limited, syntax-validated, and SHA-256 hashed from the same in-memory buffer. Leaf metadata, parent identity, and root pathname identity are checked after the read.

The allowed path set is enumerated again after syntax/hash validation. A path-set change during validation fails closed.

## Composition with the remote-update workflow

The workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

During initial Stage/Validate, the validation reader is bound to the same staging-root identity already held by `StagingFilesystem`. The resulting path/hash manifest must still exactly match the fetched Git blob manifest before the tree can be installed as staging.

Before remote apply, `assert_staging_integrity()` repeats descriptor-pinned validation and, for production staging results, requires the exact root identity captured when staging was installed. Transaction preparation and post-Backup revalidation remain independent additional continuity gates.

## Policy invariants

This hardening does not make `/homeassistant` a Git checkout and does not introduce `git pull` against live configuration. Existing secret/runtime exclusions remain unchanged, including `secrets.yaml`, `.storage`, databases, logs, key/certificate material, PID/lock/temp files, and `.git` content.

A confinement or identity failure is a validation failure. It must not be converted into a best-effort pathname read or ignored to keep an update moving.
