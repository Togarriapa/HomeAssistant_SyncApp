# Staging root identity binding

Validated staging is not trusted solely because a later pathname contains the same files and hashes.

During remote materialization, `StagingFilesystem` already pins the newly created staging tree by device/inode while fetched Git blobs are written and validated. SyncApp now carries that exact root identity in the production `StagingResult` after the tree is installed at `/data/staging`.

Before remote apply planning, `assert_staging_integrity()` requires the staging pathname to still identify that exact directory inode, performs the existing path/count/size/SHA-256 validation, and checks the root identity again afterwards. A whole-tree rename/replacement therefore fails even when the replacement is a real directory containing byte-identical policy-approved files.

Legacy/unit fixtures that intentionally construct an integrity-bound `StagingResult` without filesystem identity continue to exercise the older hash-manifest contract. Production `stage_remote_configuration()` always supplies root identity evidence.

This strengthens the Validate boundary without changing the remote-update sequence:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No Git operation is performed against `/homeassistant`, and blocked secret/runtime paths remain excluded by the existing policy.
