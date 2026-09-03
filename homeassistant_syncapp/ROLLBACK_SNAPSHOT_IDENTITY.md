# Rollback snapshot root identity binding

Rollback files are accepted only from the exact snapshot tree that was captured or validated as transaction evidence, not merely from a later pathname containing matching bytes.

During normal transaction preparation, SyncApp records the rollback snapshot root device/inode immediately after creating the snapshot directory and verifies that identity again after snapshot capture. The identity stays with the in-process `FileTransaction`.

During interrupted recovery, `TransactionEvidenceRoot.snapshot_hashes()` opens the snapshot root relative to the already-pinned transaction-root descriptor with `O_DIRECTORY | O_NOFOLLOW`, recursively validates the snapshot hashes and entry identities, and retains the device/inode from that same opened descriptor. `load_active_transaction()` carries that validated identity into the recovered `FileTransaction`.

Before rollback, the snapshot pathname must still identify the expected root. More importantly, the expected identity is passed into `LiveFilesystem.replace_from()`, which compares it with the descriptor-safe source root it actually opens immediately before copying restore bytes. A byte-identical whole-snapshot substitution after prechecks therefore fails before live `os.replace()`.

The identity is runtime recovery evidence and does not alter the journal schema. Existing journal SHA-256/path-set checks remain mandatory and complementary: hashes prove content, while root identity proves that the content comes from the same validated filesystem tree.

The remote-update sequence remains unchanged:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

Rollback failure preserves transaction evidence for diagnosis/retry; no blind Git operation is introduced against `/homeassistant`, and secret/runtime exclusions are unchanged.
