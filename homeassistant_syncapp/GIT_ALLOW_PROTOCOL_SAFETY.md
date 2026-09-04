# Ambient Git protocol whitelist safety

SyncApp's managed Git transport policy is explicit: production GitHub repositories deny protocols by default and permit HTTPS. That command-scope policy must remain authoritative.

Git also recognizes `GIT_ALLOW_PROTOCOL`. When present, this environment variable acts as a protocol whitelist and overrides existing `protocol.*.allow` configuration. An inherited value could therefore silently broaden transport eligibility beyond the policy installed by SyncApp.

SyncApp now removes `GIT_ALLOW_PROTOCOL` from the process environment before constructing the synchronization engine. The existing command-scope transport policy then determines which production protocols are available, while offline test repositories retain their intentionally separate local-transport behavior.

This complements `GIT_PROTOCOL_FROM_USER=0`: one prevents ambient user-authorization state from enabling `user` protocols, while this boundary removes the stronger environment-level protocol whitelist override.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
