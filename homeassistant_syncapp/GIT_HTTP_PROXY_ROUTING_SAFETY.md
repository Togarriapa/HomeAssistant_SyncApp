# Git HTTP proxy routing safety

SyncApp treats its configured GitHub HTTPS repository as an authoritative transport target. Proxy routing must not be able to change implicitly through inherited environment state or persistent repository-local Git configuration.

For every Git subprocess, SyncApp now:

- removes conventional HTTP(S)/all-proxy and no-proxy environment variables in both lowercase and uppercase forms;
- clears generic `http.proxy` at command scope;
- clears the proxy value for the exact configured repository URL;
- clears the proxy value for SyncApp's internal authoritative transport alias.

The exact URL resets are important because Git chooses the best matching `http.<url>.*` subsection, and a longer path-specific repository setting can outrank a generic `http.proxy` fallback. SyncApp therefore binds the no-proxy decision at the same URL identities used for authoritative Fetch and Push instead of relying on a generic reset alone.

This policy is deliberately direct-only. SyncApp does not yet expose an explicit trusted proxy option, so a deployment that requires an HTTP(S) proxy must wait for a separately reviewed transport-configuration contract rather than injecting proxy routing through `.git/config` or the add-on environment.

This milestone does not change CA roots, client certificates, TLS verification, authorization headers, GitHub URL provenance, or managed-content filtering.

The live update contract remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. `/homeassistant` is not a Git worktree, no blind `git pull` is used, and secret/runtime exclusions are unchanged.
