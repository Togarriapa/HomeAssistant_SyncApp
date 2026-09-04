# Git proxy command safety

Repository-local Git configuration must not be able to select an arbitrary process as the transport proxy for SyncApp Git subprocesses.

Git's `core.gitProxy` setting can name a command that Git executes for the native `git://` transport. That makes `.git/config` an execution boundary even when the repository root and metadata directory identities are already descriptor-pinned.

SyncApp therefore installs a command-scope `core.gitProxy=none` value for every Git subprocess. This setting overrides repository-local `core.gitProxy` values. Ambient `GIT_PROXY_COMMAND` is also removed before the child environment is constructed.

This control is deliberately separate from HTTPS proxy and TLS policy. It prevents repository-controlled proxy *process execution* without changing the configured authoritative repository URL or the existing transport-alias provenance protections.

The Home Assistant safety contract is unchanged: `/homeassistant` remains outside Git, secret/runtime exclusions remain intact, no blind `git pull` is permitted, and remote application remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**.
