# Git user-protocol safety

SyncApp is a non-interactive synchronization service. Git transport decisions must come from the application's explicit repository policy, not from ambient state that tells Git to treat a protocol as directly user-authorized.

Git documents `GIT_PROTOCOL_FROM_USER=false` as preventing protocols whose policy is `user` from being used by fetch, push, or clone. This is intended for programs that feed potentially untrusted URLs to Git or otherwise need to prevent nested Git operations from inheriting user authorization.

SyncApp now forces `GIT_PROTOCOL_FROM_USER=0` before constructing the synchronization engine. An inherited value of `1` therefore cannot broaden protocol eligibility.

This composes with the production transport policy that already denies protocols by default and explicitly permits only HTTPS for the configured GitHub repository. It is defense in depth: the fixed protocol configuration remains authoritative, while the environment can no longer re-enable any `user`-classified protocol surface that may be introduced by future Git behavior or commands.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
