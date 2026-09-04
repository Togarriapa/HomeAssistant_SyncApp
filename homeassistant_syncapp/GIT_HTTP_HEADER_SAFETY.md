# Git HTTP header safety

SyncApp treats repository-local Git configuration as untrusted control state. A persistent `.git/config` must not be able to inject additional HTTP headers into Fetch, Push, or authoritative remote verification.

Every SyncApp Git subprocess therefore installs an empty command-scope `http.extraHeader` first. Git uses the empty value to clear lower-precedence extra-header values. If a GitHub token is configured, SyncApp then adds only its own host-scoped `http.https://github.com/.extraHeader` authorization value.

This keeps transport authentication under SyncApp control and prevents repository-local header injection from composing with the configured GitHub request.

This control is additive to the existing safeguards for TLS verification, redirect policy, proxy-command execution, credential helpers, askpass/SSH helpers, URL rewrite locking, and descriptor-pinned Git metadata.

The live Home Assistant workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` is not a Git worktree. No blind `git pull` is introduced, and managed secret/runtime exclusions are unchanged.
