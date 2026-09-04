# Git transport URL rewrite safety

SyncApp deliberately uses the configured repository URL directly for authoritative Fetch and publication instead of trusting the mutable `origin` name. Git repository configuration can still contain `url.<base>.insteadOf` and `url.<base>.pushInsteadOf` rules, however. Those rules are capable of rewriting a URL passed explicitly on the Git command line.

A static rewrite is normally exposed by remote provenance checks, but provenance validation and the later transport subprocess are separate operations. A rewrite rule inserted after provenance validation must not be able to redirect authenticated Fetch or publication.

For network operations, SyncApp therefore does not pass the configured URL itself to Git. It passes an internal transport alias formed by appending a fixed SyncApp suffix to the configured URL. Command-scope Git configuration maps that exact, longer alias back to the configured URL using both `insteadOf` and `pushInsteadOf`. Git's URL rewrite selection uses the longest matching prefix; consequently a repository-local rule targeting the configured URL is a shorter match than SyncApp's exact transport alias. Command-scope configuration is also part of Git's protected configuration scope.

The alias is used only for `ls-remote`, Fetch, and Push transport invocation. Persistent `origin` remains the configured repository URL so the existing provenance checks continue to detect static retargeting. Authentication policy is still derived from the configured URL, not from repository-local rewrite state.

Failure-injection tests install malicious fetch and push rewrite rules immediately after a successful provenance check and require all traffic to continue to the configured repository while the attacker repository remains untouched.

This hardening does not change live configuration semantics. `/homeassistant` is not a Git worktree, no blind `git pull` is used, and remote updates remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary** with secret/runtime exclusions unchanged.
