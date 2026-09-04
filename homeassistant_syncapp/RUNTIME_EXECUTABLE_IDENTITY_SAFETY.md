# Runtime executable identity safety

SyncApp should not inherit an executable search path that can be widened by container or supervisor environment state. Even with the top-level Git binary pinned, Git and the application runtime may invoke trusted system helpers by name; allowing an attacker-controlled directory earlier in `PATH` would leave an unnecessary executable-substitution surface.

The add-on entrypoint now replaces inherited `PATH` with the fixed system-only value `/usr/bin:/bin` before starting the application. It also starts Python through the absolute executable `/usr/bin/python3` rather than resolving `python3` through `PATH`.

The image build verifies that both `/usr/bin/git` and `/usr/bin/python3` exist and are executable. Regression coverage binds the entrypoint ordering so the constrained search path is installed before Python starts.

This is deliberately narrower than trying to hard-code every internal Git helper location. Git's ambient `GIT_EXEC_PATH` is already scrubbed by SyncApp, while the package-provided Git installation retains its compiled helper path. The constrained process `PATH` removes ambient writable directories from fallback helper and command lookup without changing the explicit remote-update protocol or repository evidence rules.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and exclusions for secrets, `.storage`, databases, logs, keys/certificates, runtime state, and Git control files are unchanged.
