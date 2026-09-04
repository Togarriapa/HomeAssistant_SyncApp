# Git HTTP redirect safety

SyncApp treats the configured Home Assistant repository URL as an authoritative transport target. Repository-local Git configuration must not be able to broaden that authority after provenance validation.

Every SyncApp Git subprocess therefore forces:

```text
http.followRedirects=initial
```

This preserves Git's normal compatibility behavior for an initial HTTP redirect while preventing repository-local `.git/config` from enabling unrestricted redirect following for later requests in a Git HTTP exchange.

This control composes with the existing transport protections: the configured repository is restricted to HTTPS GitHub, TLS verification is forced on, proxy-command execution is disabled, authentication helpers are constrained, transport URL rewriting is pinned to the configured target, and Fetch/Push are verified against authoritative remote state.

The live Home Assistant workflow is unchanged:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside the Git worktree. This change does not add a blind `git pull`, does not alter managed-path selection, and does not weaken exclusions for secrets or runtime files.
