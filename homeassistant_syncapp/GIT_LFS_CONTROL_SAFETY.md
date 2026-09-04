# Git LFS control-file safety

SyncApp treats remotely managed Home Assistant configuration as data, not as Git control state.

`.lfsconfig` is therefore blocked at every managed path depth. Git LFS can read repository-controlled configuration from this file, including transfer-endpoint settings. SyncApp does not currently use Git LFS, but accepting `.lfsconfig` would leave a dormant repository-controlled transport surface that could become active if the Git command surface changes later.

This exclusion applies in both directions:

- local Home Assistant publication does not mirror `.lfsconfig` into the managed Git repository;
- remote staging rejects `.lfsconfig` rather than treating it as Home Assistant configuration.

The rule is defense in depth and does not replace the existing protections around Git transport provenance, descriptor-pinned repository metadata, or exact staged/committed tree validation.

The remote-update lifecycle remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No Git operation is permitted to turn `/homeassistant` into a Git worktree, and existing secret/runtime exclusions remain mandatory.
