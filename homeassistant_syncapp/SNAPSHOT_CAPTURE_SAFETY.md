# Rollback snapshot capture safety

The Backup phase must create rollback evidence without following mutable destination pathnames. SyncApp therefore confines snapshot capture to descriptors on both sides of the copy.

The live source file is opened relative to descriptor-safe `/homeassistant` traversal with `O_NOFOLLOW` and must be a regular file. The rollback snapshot root identity is captured immediately after the transaction creates the snapshot directory. `LiveFilesystem.copy_to()` receives that exact device/inode identity and opens the snapshot root with `O_DIRECTORY | O_NOFOLLOW` before any snapshot bytes are written.

Nested snapshot parents are opened relative to already-pinned directory descriptors. Missing parents are created with `mkdir(..., dir_fd=...)`, their parent directory is fsynced, and the new directory is reopened with `O_DIRECTORY | O_NOFOLLOW`. Existing symlinks or non-directory components are refused. Every opened parent entry is required to keep identifying the same directory after capture.

The snapshot leaf is created exclusively with `O_EXCL | O_NOFOLLOW`. Live bytes are streamed from the pinned source descriptor directly into that opened snapshot descriptor while SHA-256 is computed over the exact copied bytes. The file descriptor is fsynced, its entry must still identify the exact regular inode that was written, and the pinned snapshot parent directory is fsynced so the leaf creation is durable.

Before accepting the capture, SyncApp rechecks each nested parent entry and requires the snapshot-root pathname to still identify the original opened root. A root or nested-parent rename/replacement during capture therefore fails closed. On failure, SyncApp removes only the snapshot leaf it created, using the still-pinned original parent descriptor; a replacement tree is never traversed or modified by cleanup.

The live source is hashed again through its still-open descriptor after snapshot capture. If the live file changed during capture, the snapshot is rejected rather than becoming trusted rollback evidence.

These checks complement the later journal/snapshot SHA-256 validation and rollback source-root identity checks. They do not change the required remote-update sequence:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No Git operation is performed against `/homeassistant`, and secret/runtime-file exclusions remain unchanged.
