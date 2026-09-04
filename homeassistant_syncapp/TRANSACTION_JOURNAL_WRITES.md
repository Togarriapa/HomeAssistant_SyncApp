# Transaction journal write confinement

Transaction recovery evidence must remain trustworthy while SyncApp is actively preparing, applying, verifying, or rolling back a remote update. Recovery reads are descriptor-pinned; journal writes now use the same filesystem trust boundary.

A newly created transaction records the device/inode identity of its transaction root. Interrupted recovery obtains that identity from the same pinned `TransactionEvidenceRoot` descriptor used to validate the journal and snapshot, then carries it into the recovered `FileTransaction`.

Every journal state update opens the transaction root with `O_DIRECTORY | O_NOFOLLOW` and requires the opened directory to match the expected device/inode. The update is serialized to an exclusively created no-follow temporary file relative to that directory descriptor, fsynced, atomically replaced onto `journal.json` using source and destination `dir_fd`, and followed by an fsync of the transaction directory.

The transaction-root pathname is required to still identify that opened directory before temporary creation, before atomic replacement, and after directory fsync. If the root is renamed or replaced, SyncApp fails closed rather than writing recovery state into a different tree. A pre-existing temporary entry is preserved and treated as ambiguous evidence; it is never followed or overwritten.

Journal state in memory advances only after the durable descriptor-confined update and final pathname identity proof succeed. This keeps the state machine aligned with the recovery evidence actually persisted on disk.

This is an incremental write-side hardening boundary. Snapshot capture, live mutation, recovery validation, source-copy confinement, and rollback identity checks remain independent mandatory gates in the same workflow:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No Git operation is performed against `/homeassistant`, and secret/runtime exclusions are unchanged.
