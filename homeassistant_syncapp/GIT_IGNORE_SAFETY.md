# Git ignore safety boundary

SyncApp treats managed Home Assistant configuration as an explicit validated file set. Git ignore rules are control-plane instructions that can change which untracked worktree paths `git add -A` considers for staging, so they are not part of that data set.

`.gitignore` is therefore blocked at every path depth. Local Home Assistant files with that name are not published, and remote repositories cannot make them managed live configuration. The staged-tree and manifest checks remain authoritative, but excluding ignore rules removes an unnecessary source of Git-side interpretation before those checks run.

This is a stricter policy boundary only. It does not relax or replace the existing exclusions for `secrets.yaml`, `.storage`, databases, logs, runtime files, private keys/certificates, or `.git` metadata.

The update sequence remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No Git pull is performed against `/homeassistant`; Git operations stay confined to the isolated repository under `/data`.
