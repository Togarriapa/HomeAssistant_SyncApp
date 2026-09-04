# Git ambient proxy safety

SyncApp currently supports an explicit GitHub HTTPS repository target, but it does not expose a trusted proxy configuration option. Inherited process variables therefore must not be allowed to silently change the network route used for GitHub synchronization.

At process startup SyncApp removes the conventional `http_proxy`, `https_proxy`, `all_proxy`, and `no_proxy` variables, including their uppercase variants, before constructing the synchronization engine. This makes ambient add-on/container proxy state non-authoritative for Git transport.

This is intentionally fail closed. Deployments that require an HTTP(S) proxy are not yet modeled as a trusted SyncApp transport configuration and should not depend on ambient environment injection.

## Scope boundary

This milestone closes the inherited environment half of proxy routing only. Repository-local Git configuration such as `http.proxy` or URL-specific `http.<url>.proxy` remains a separate control-plane surface. A generic command-scope `http.proxy=` is not sufficient against a more specific repository-local URL match, so that boundary must be neutralized using an exact configured-repository URL override rather than an incomplete blanket reset.

The change does not alter certificate authorities, client certificates, TLS verification policy, GitHub authorization headers, or the managed Home Assistant content exclusions.

The remote update workflow remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. Git remains isolated under `/data`; `/homeassistant` is never turned into a Git worktree and no blind `git pull` is introduced.
