# Staging root identity binding

Validated staging is not trusted solely because a later pathname contains the same files and hashes.

During remote materialization, `StagingFilesystem` pins the newly created staging tree by device/inode while fetched Git blobs are written and validated. SyncApp carries that exact root identity in the production `StagingResult` after the tree is installed at `/data/staging`.

Before remote apply planning, `assert_staging_integrity()` requires the staging pathname to still identify that exact directory inode, performs the existing path/count/size/SHA-256 validation, and checks the root identity again afterwards. A whole-tree rename/replacement therefore fails even when the replacement is a real directory containing byte-identical policy-approved files.

For a mutating apply, the same identity is passed into `FileTransaction`. When `LiveFilesystem.replace_from()` later opens the staging source root with `O_DIRECTORY | O_NOFOLLOW`, it compares the opened root descriptor's device/inode to the identity captured during validated staging before any source bytes can become a live replacement. This closes the later window between pre-apply validation, Supervisor backup work, and actual live mutation: a byte-identical staging-root substitution after transaction preparation is still rejected before the live `os.replace()`.

The root identity is runtime evidence rather than recovery journal state. Interrupted transactions never resume a forward staging apply; they follow the existing rollback/recovery path instead.

Legacy/unit fixtures that intentionally construct an integrity-bound `StagingResult` without filesystem identity continue to exercise the older hash-manifest contract. Production `stage_remote_configuration()` always supplies root identity evidence. Existing direct `replace_from()` callers remain compatible because expected source-root identity is an optional, keyword-only proof; production remote apply supplies it.

This strengthens the Validate-to-Apply evidence chain without changing the remote-update sequence:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No Git operation is performed against `/homeassistant`, and blocked secret/runtime paths remain excluded by the existing policy.
