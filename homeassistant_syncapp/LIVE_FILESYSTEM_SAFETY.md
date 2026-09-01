# Live filesystem safety boundary

SyncApp treats `/homeassistant` as a live, concurrently mutable filesystem. Remote Git content is never checked out or pulled directly into that tree.

For transaction preparation, apply, and rollback, SyncApp opens the live configuration root as a directory with `O_NOFOLLOW`, then opens each parent component relative to the previously opened directory descriptor. Leaf reads, atomic replacements, and deletions are performed relative to that already-open parent descriptor.

This matters because pathname validation followed by a later pathname mutation has a time-of-check/time-of-use window: a parent component could be replaced with a symlink after validation and before `replace` or `unlink`. Descriptor-relative operations avoid resolving that parent pathname again for the final mutation.

The live filesystem layer therefore:

- refuses symlinked roots, parent components, and leaf targets;
- never accepts paths that fail the normal secret/runtime policy;
- creates missing parent directories relative to a verified open directory and fsyncs the parent;
- creates transaction temporary files with `O_EXCL|O_NOFOLLOW`;
- writes and fsyncs the temporary file before descriptor-relative atomic replacement;
- fsyncs the actual opened parent directory after replacement or deletion;
- snapshots rollback evidence and hashes live files through no-follow descriptors;
- removes its temporary file when copying or hash verification fails before replacement.

This is defense in depth beneath the transaction workflow. It does not replace staging validation, Supervisor backup, `/core/check`, restart/health verification, Git provenance checks, transaction journaling, or rollback.

The required remote workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

Real Home Assistant OS validation must confirm that the container/runtime filesystem supports the descriptor-relative operations and durability assumptions used here before remote apply is considered production-ready.
