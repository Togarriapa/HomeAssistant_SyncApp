# Transaction integrity revalidation safety

Remote updates preserve the required sequence:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

The staging tree and rollback snapshot are mutable filesystem evidence. Their SHA-256 manifests are necessary, but pathname-based re-opening is not sufficient: a parent directory, leaf, or whole root can be replaced between an earlier identity check and the file read.

## Descriptor-pinned revalidation

`FileTransaction.assert_staging_unchanged()` and `assert_snapshot_unchanged()` now read evidence through `PinnedReadRoot`.

For each revalidation the implementation:

1. opens the evidence root with `O_DIRECTORY | O_NOFOLLOW`;
2. requires the opened root to match the previously validated device/inode identity when one is available;
3. traverses nested parents relative to already-open directory descriptors and refuses symlink/non-directory parents;
4. opens the leaf with `O_NOFOLLOW` and requires a regular file;
5. hashes bytes from that exact opened descriptor;
6. requires device/inode/size/mtime/ctime stability across the read;
7. re-checks the leaf directory entry and every opened parent entry;
8. finally proves that the root pathname still identifies the opened root.

A race therefore fails closed instead of causing integrity evidence to be accepted from a replacement pathname.

## Rollback behavior

Rollback no longer performs an additional pathname-based `is_file()`/SHA-256 pass immediately before restore. Snapshot integrity is proven by the descriptor-pinned revalidation gate, and `LiveFilesystem.replace_from()` independently opens the rollback source through its descriptor-confined source boundary and requires the expected snapshot-root identity and SHA-256 before live replacement.

This keeps the two independent protections that matter—pre-rollback evidence validation and descriptor-safe source copying—without inserting an unsafe pathname read between them.

## Scope

This change does not alter Git behavior, does not operate Git against `/homeassistant`, does not weaken the managed-path policy, and does not permit secret/runtime files into the managed set. Supervisor Backup remains mandatory before any live mutation.
