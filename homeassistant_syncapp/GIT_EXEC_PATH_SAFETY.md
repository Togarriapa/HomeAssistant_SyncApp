# Git internal helper path safety

Pinning `/usr/bin/git` prevents substitution of the top-level Git executable, but Git can also execute package-provided helper programs such as `git-remote-https`. An inherited `GIT_EXEC_PATH` can redirect that internal helper lookup to a different directory.

SyncApp now removes any inherited `GIT_EXEC_PATH` and replaces it with the image-owned Alpine Git helper directory `/usr/libexec/git-core` for every managed Git subprocess. The add-on image build verifies that `/usr/bin/git --exec-path` reports that exact directory and that the HTTPS remote helper exists and is executable there.

Regression coverage poisons inherited `GIT_EXEC_PATH` and verifies both the constructed child environment and Git's own `--exec-path` result resolve only to `/usr/libexec/git-core`.

This composes with the absolute `/usr/bin/git` executable, the system-only process `PATH`, HTTPS-only production transport policy, disabled credential/hook/filter execution surfaces, and the existing command-scope Git configuration locks.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
