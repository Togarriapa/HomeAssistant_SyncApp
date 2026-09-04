# Safe recovery of an unpushed local commit

A failed network push can leave SyncApp's isolated managed branch ahead of the configured remote. That state must not turn the next polling cycle into a blind `git push` of whatever history happens to exist under `/data`.

SyncApp permits automatic retry only when exactly one commit would be sent. This applies both to `local_ahead` (a configured remote branch exists) and `local_only` (for example, the first validated publication was committed but its initial push failed before the remote branch was created). Multiple unpushed commits are refused so an apparently safe final tree cannot conceal an unsafe intermediate commit such as secret material in Git history.

Before retrying, SyncApp enumerates the immutable HEAD commit tree with Git plumbing. Every entry must be a policy-approved regular blob with supported mode, and the SHA-256 path/content manifest of the commit must exactly match descriptor-validated live Home Assistant configuration. Home Assistant semantic configuration validation is then run, followed by a second descriptor validation of live bytes. A mismatch or mutation fails closed and leaves the unpushed commit local for operator investigation.

Only after those checks does SyncApp retry the configured-origin push. On success, the managed-path manifest is persisted from the exact committed path set.

This recovery path never changes live Home Assistant configuration. Remote updates remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. No blind `git pull` touches `/homeassistant`, and secret/runtime exclusions remain unchanged.
