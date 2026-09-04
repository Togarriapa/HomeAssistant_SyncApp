# Git authentication and SSH helper safety

Repository-local Git configuration must not be able to turn SyncApp transport or authentication handling into arbitrary process execution.

SyncApp already removes ambient `GIT_ASKPASS`, `SSH_ASKPASS`, and `GIT_SSH_COMMAND` values before launching Git. It now installs fixed safe replacements after scrubbing:

- `GIT_ASKPASS=/dev/null`
- `SSH_ASKPASS=/dev/null`
- `GIT_SSH_COMMAND=ssh`

The askpass settings fail closed instead of allowing repository or ambient configuration to select an executable credential-prompt helper. The SSH command environment override takes precedence over repository-local `core.sshCommand`, preventing `.git/config` from selecting an arbitrary SSH wrapper while preserving ordinary SSH transport behavior.

These controls compose with command-scope `core.fsmonitor=false`, disabled hooks, disabled credential helpers, global/system config suppression, descriptor-pinned repository metadata, and authoritative transport URL locking.

This change does not weaken any Home Assistant content boundary. `/homeassistant` remains outside Git; no blind `git pull` is used; secret/runtime exclusions stay intact; and remote application remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**.
