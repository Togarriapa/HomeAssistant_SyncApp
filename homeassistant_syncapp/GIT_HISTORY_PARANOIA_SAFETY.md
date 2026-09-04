# Git history integrity paranoia

SyncApp treats Git refs, commits, trees, and blobs as transaction evidence. Ambient recovery-oriented settings must not make Git silently overlook broken reference state or trust stale commit-graph entries.

Git normally enables `GIT_REF_PARANOIA`: broken or badly named refs are included during ref iteration so operations can fail rather than silently ignore history. An inherited `GIT_REF_PARANOIA=0` would weaken that fail-closed default. SyncApp therefore forces it to `1`.

Git also provides `GIT_COMMIT_GRAPH_PARANOIA`. Enabling it makes Git verify that a commit loaded from commit-graph metadata actually exists in the object database, preventing stale commit-graph entries from being returned as usable commits. SyncApp forces this check to `1` as well; the extra object existence check is appropriate for an integrity-sensitive synchronization service.

These settings do not create, prune, or rewrite refs or history. They only make Git reject inconsistent evidence more aggressively.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
