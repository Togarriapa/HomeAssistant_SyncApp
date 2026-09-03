# Managed-path manifest persistence safety

The managed-path manifest is control state. Its persistence path must never become an alternate route for modifying live Home Assistant files outside the guarded remote-apply transaction.

`load_manifest()` opens the manifest relative to an opened no-follow parent directory descriptor. The manifest leaf itself is opened with `O_NOFOLLOW`, must be a regular file, is bounded to 1 MiB, and is checked for metadata/pathname continuity while being read. A symlinked manifest is rejected rather than followed.

`save_manifest()` serializes and bounds the payload before creating an exclusive transaction-owned temporary leaf with `O_CREAT | O_EXCL | O_NOFOLLOW` relative to the opened parent descriptor. A pre-existing temporary file or symlink is refused and is not deleted because SyncApp does not own it. The payload is fsynced, the parent identity is rechecked, and the temporary leaf is atomically replaced onto the manifest name with descriptor-relative `os.replace()`. Parent-directory durability is then proven with fsync against the expected directory identity.

If creation, replacement, or durability proof fails, SyncApp reports a `ManifestError`; it never falls back to ordinary pathname writes.

Remote updates are unchanged and remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. No blind `git pull` touches `/homeassistant`, and existing secret/runtime exclusions remain unchanged.
