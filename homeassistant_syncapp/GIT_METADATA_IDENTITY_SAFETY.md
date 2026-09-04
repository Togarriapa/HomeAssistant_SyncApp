# Git metadata identity safety

Pinning the isolated `/data` repository root prevents a pathname swap from redirecting a Git subprocess into a replacement worktree. Git still discovers repository metadata through `.git`, however, so the metadata directory is a separate safety-critical identity boundary.

For established repositories, SyncApp opens `.git` relative to the already pinned repository-root descriptor with `O_DIRECTORY | O_NOFOLLOW`. The first safe open binds the `GitRepository` instance to the metadata directory's device/inode identity. Later commands must observe that same identity.

When `.git` is present, SyncApp explicitly sets `GIT_DIR` and `GIT_WORK_TREE` for the child process to inherited `/proc/self/fd/<fd>` descriptors and passes both descriptors into the Git subprocess. A rename/replacement of `.git` after those descriptors are opened therefore cannot redirect the running command into replacement metadata. After each command, SyncApp proves that the `.git` directory entry still identifies the exact opened metadata directory; replacement during a command fails closed even if Git completed successfully against the detached original metadata.

Replacement or disappearance between Git commands is rejected before another command can run. Bootstrap `git init` remains root-descriptor-bound while `.git` does not yet exist; the first subsequent command binds the newly created metadata directory.

This boundary does not weaken remote provenance, configured-URL Fetch/publication, or live filesystem policy. `/homeassistant` is never a Git worktree, and remote updates remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary** with secret/runtime exclusions unchanged.
