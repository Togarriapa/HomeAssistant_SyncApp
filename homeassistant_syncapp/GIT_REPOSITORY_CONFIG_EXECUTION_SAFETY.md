# Repository-local Git execution safety

The isolated Git repository under `/data` is control state, not Home Assistant configuration data. Pinning the repository root and `.git` directory identities prevents pathname substitution, but it does not by itself make every value stored in `.git/config` safe to execute.

Git's `core.fsmonitor` setting can name an external filesystem-monitor command. A persistent repository-local value must therefore never be allowed to turn a routine SyncApp Git subprocess into execution of repository-controlled code.

SyncApp installs a command-scope `core.fsmonitor=false` override for every Git subprocess. Command-scope configuration takes precedence over repository-local configuration, so even if `.git/config` is modified between operations, SyncApp does not invoke a configured fsmonitor helper. Existing hook suppression (`core.hooksPath=/dev/null`), credential-helper suppression, ambient Git-environment scrubbing, descriptor-pinned repository metadata, and authoritative transport protections remain in force.

This is intentionally a narrow first slice of repository-local Git configuration hardening. Other security-relevant transport or helper settings should be constrained independently with focused tests rather than freezing all legitimate Git bookkeeping.

This change does not alter the live update lifecycle. `/homeassistant` remains outside Git, no blind `git pull` is used, secret/runtime exclusions remain strict, and remote application remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**.
