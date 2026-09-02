# Live filesystem safety boundary

SyncApp treats `/homeassistant` as a live, concurrently mutable filesystem. Remote Git content is never checked out or pulled directly into that tree.

For apply planning, transaction preparation, apply, and rollback, SyncApp opens the live configuration root as a directory with `O_NOFOLLOW`, then opens each parent component relative to the previously opened directory descriptor. Leaf reads, hashes, atomic replacements, and deletions are performed relative to that already-open parent descriptor.

This matters before mutation as well as during mutation. A pathname-based "is this staged file already identical to live?" optimization could follow a symlinked parent outside `/homeassistant`. If those outside bytes happened to equal the staged candidate, SyncApp could incorrectly classify the candidate as a no-op and reach Git/manifest adoption without ever entering the transaction layer that would otherwise reject the unsafe parent. Apply planning therefore uses the same no-follow descriptor boundary and fails closed on an unsafe live root, parent, or leaf even when the apparent bytes match.

This is particularly important during remote-authoritative first bootstrap. Bootstrap intentionally cannot rely on the ordinary managed-baseline drift relationship, so a supposedly unchanged staged path must still be proven to resolve inside the safely opened live configuration tree before no-op semantic validation or baseline adoption is allowed.

The live filesystem layer therefore:

- refuses symlinked roots, parent components, and leaf targets during both comparison and mutation;
- never accepts paths that fail the normal secret/runtime policy;
- compares staged candidates to live files using descriptor-relative SHA-256 reads rather than pathname `read_bytes()`;
- creates missing parent directories relative to a verified open directory and fsyncs the parent;
- creates transaction temporary files with `O_EXCL|O_NOFOLLOW`;
- writes and fsyncs the temporary file before descriptor-relative atomic replacement;
- fsyncs the actual opened parent directory after replacement or deletion;
- snapshots rollback evidence and hashes live files through no-follow descriptors;
- removes its temporary file when copying or hash verification fails before replacement.

The descriptor-safe planning check runs before the no-op adoption branch. If a symlinked parent points to an outside regular file with bytes identical to the staged candidate, planning fails; SyncApp does not instantiate Supervisor, fetch/adopt the remote baseline, persist a manifest, or modify the outside file.

This is defense in depth beneath the transaction workflow. It does not replace staging validation, Supervisor backup, `/core/check`, restart/health verification, Git provenance checks, transaction journaling, or rollback.

The required remote workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

Real Home Assistant OS validation must confirm that the container/runtime filesystem supports the descriptor-relative operations and durability assumptions used here before remote apply is considered production-ready.
