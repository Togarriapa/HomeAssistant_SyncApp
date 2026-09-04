# Git curl verbose safety

SyncApp already removes Git trace variables before transport subprocesses, but Git also supports the older `GIT_CURL_VERBOSE` environment control. Git documents that variable as enabling libcurl's verbose transport messages.

Because SyncApp may attach a GitHub authorization header, inherited verbose transport diagnostics are not part of the trusted runtime contract. Before the synchronization engine starts, SyncApp removes `GIT_CURL_VERBOSE` from the process environment. The existing `GIT_TRACE*` scrub remains in place as the complementary modern trace boundary.

This change does not alter normal SyncApp logging, transport routing, certificate verification, CA trust, or GitHub authentication. It only prevents ambient runtime state from enabling low-level curl diagnostics for Git subprocesses.

The live update contract remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. `/homeassistant` remains outside Git, no blind `git pull` is used, and secret/runtime exclusions are unchanged.
