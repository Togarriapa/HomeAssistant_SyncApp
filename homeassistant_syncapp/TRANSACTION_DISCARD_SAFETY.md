# Transaction discard safety

Transaction cleanup must never turn a pathname race into recursive deletion of an unrelated replacement tree.

`FileTransaction.discard()` requires the transaction-root device/inode identity captured when the transaction was created or descriptor-safely recovered. Cleanup opens the transaction parent with `O_DIRECTORY | O_NOFOLLOW`, opens the transaction root relative to that parent, and requires the opened root descriptor and parent directory entry to identify the expected directory before recursive removal begins.

Recursive cleanup enumerates and removes entries only through already-open directory descriptors. Child directories are opened with `O_DIRECTORY | O_NOFOLLOW`, compared with their parent directory entries, recursively cleared through their descriptors, rechecked, and removed relative to the pinned parent. Regular files and symlinks are unlinked relative to the pinned parent after an identity/type recheck; symlinks are never followed. Special filesystem entries fail closed.

If the transaction-root pathname is renamed or replaced after cleanup has started, recursive deletion continues only inside the originally opened transaction directory. Before final root removal, the parent entry must still identify that exact opened root. A replacement root therefore is not traversed or recursively deleted. The cleanup fails closed and preserves the replacement tree while the detached original evidence may remain for diagnosis.

After the final `rmdir`, SyncApp verifies through the still-open original root descriptor that its link count reached zero, then fsyncs the pinned parent directory. This proves that successful cleanup removed the exact transaction tree that was authorized, not merely some directory currently occupying the same pathname.

The cleanup contract complements descriptor-safe journal writes, rollback snapshot capture/validation, source-copy confinement, and rollback restore identity. It does not change the remote-update sequence:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No Git operation is performed against `/homeassistant`, and secret/runtime-file exclusions remain unchanged.
