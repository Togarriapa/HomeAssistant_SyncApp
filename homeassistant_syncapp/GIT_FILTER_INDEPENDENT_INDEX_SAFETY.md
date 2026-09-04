# Filter-independent Git index construction

SyncApp treats the isolated repository under `/data` as transaction evidence, not as a place where repository-controlled Git attributes may transform Home Assistant configuration bytes.

`$GIT_DIR/info/attributes` is a high-precedence Git attribute source. Unlike managed `.gitattributes`, it lives inside Git metadata and can select `filter.<name>.clean` or process filters even when global/system attribute files are disabled. A pathname pre-check would not be sufficient because the metadata file could appear or change between that check and an ordinary `git add`.

Local publication therefore no longer asks `git add` to discover or convert managed files. `GitRepository.add_all()` now:

1. validates the existing `HEAD` tree before rebuilding the index and rejects blocked paths, non-blob entries, or unsupported file modes;
2. enumerates only policy-approved regular files through `PinnedReadRoot`, which pins the isolated repository root and does not follow mutable directory or leaf symlinks;
3. reads each candidate's exact bytes through that pinned evidence handle;
4. writes those bytes with `git hash-object --no-filters --stdin`, so Git attributes cannot invoke clean/smudge/process transformations;
5. rebuilds the index explicitly with `git update-index --cacheinfo`, preserving a safe baseline executable mode where one already exists and using `100644` for new managed files;
6. re-enumerates the pinned worktree and fails closed if its approved path set changed during construction.

Starting from an empty index intentionally stages deletions: a previously tracked managed path that is no longer present in the approved mirror is absent from the reconstructed candidate tree. The existing staged-tree SHA-256 comparison remains the final proof that indexed blob bytes exactly match the statically validated mirror before semantic Home Assistant validation and publication.

This design means a malicious or concurrently-created `$GIT_DIR/info/attributes` can remain present without gaining an execution path during managed index construction. SyncApp does not delete or mutate that metadata file; it simply makes the staging operation independent of attribute-driven filters.

Protected source exclusions are unchanged. `secrets.yaml`, `.storage`, databases, logs, runtime files, key/certificate material, Git control files, and other blocked paths are still excluded before publication. A blocked path already committed in the managed baseline causes index construction to fail closed rather than being silently normalized away.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No blind `git pull` is introduced, and `/homeassistant` is never made a Git worktree.
