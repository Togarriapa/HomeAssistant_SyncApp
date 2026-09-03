# Apply source filesystem safety

SyncApp treats both validated staging files and rollback snapshot files as mutable filesystem evidence until their bytes are copied into the live Home Assistant configuration.

The live destination has already been descriptor-confined. This milestone closes the corresponding source-side gap in `LiveFilesystem.replace_from()`.

## Source proof before live replacement

For every write, SyncApp derives the expected source root from the policy-approved relative path and the supplied source path. It then:

1. opens the source root with `O_DIRECTORY | O_NOFOLLOW`;
2. walks every nested parent with descriptor-relative `os.open(..., dir_fd=...)` and `O_NOFOLLOW`;
3. opens the source leaf relative to the already-open parent with `O_NOFOLLOW`;
4. requires the leaf to be a regular file;
5. records source file device, inode, size, mtime, ctime, and file type;
6. streams the source through the pinned file descriptor into an exclusive live-side temporary file while hashing the exact copied bytes;
7. requires the copied SHA-256 to equal the transaction's expected digest;
8. rechecks the opened file metadata and the source leaf directory entry;
9. rechecks every parent directory entry in the opened source chain;
10. rechecks that the source-root pathname still identifies the opened source root;
11. only after all source proofs succeed atomically replaces the live destination through its already-open parent descriptor.

A source-root rename, nested-parent replacement, symlink insertion, leaf replacement, or in-place file mutation therefore fails before the live destination replacement.

## Why the SHA-256 check is not enough

The transaction already binds staged writes to validated SHA-256 values and rollback writes to snapshot SHA-256 values. A digest proves content identity, but by itself it does not prove that the bytes came from the expected filesystem object or that the source pathname remained attached to the object that was inspected.

Descriptor-relative source traversal composes with the digest proof:

**expected source tree → pinned directory chain → pinned regular-file descriptor → exact SHA-256 → stable source identity → descriptor-safe live replacement**

## Failure behavior

If any source proof fails, SyncApp removes the exclusive live-side temporary file and does not execute the destination `os.replace()`. Existing live configuration therefore remains untouched by that write.

Rollback uses the same `replace_from()` boundary, so interrupted-transaction recovery receives the same source confinement when restoring snapshot bytes.

## Workflow preservation

Remote updates remain:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

This change does not add Git operations against `/homeassistant`, does not weaken secret/runtime exclusions, and does not bypass the mandatory Supervisor backup gates before live mutation.
