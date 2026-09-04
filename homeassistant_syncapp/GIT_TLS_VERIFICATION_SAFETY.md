# Git TLS verification safety

Repository-local Git configuration and inherited process state must not be able to silently disable certificate verification for SyncApp network operations.

SyncApp therefore removes inherited `GIT_SSL_NO_VERIFY` and installs command-scope values for every Git subprocess:

- `http.sslVerify=true`
- `http.proxySSLVerify=true`

These command-scope settings override repository-local values such as `http.sslVerify=false` or `http.proxySSLVerify=false`, preserving server and HTTPS-proxy certificate verification even if persistent `.git/config` is modified between application cycles.

This slice deliberately does not pin a CA bundle, proxy destination, or client-certificate path. Those settings can be deployment-specific and require separate compatibility analysis before they can be constrained safely. The goal here is narrower: repository state cannot downgrade verification itself.

This composes with the existing authoritative remote URL lock, Git proxy-command neutralization, fixed SSH/authentication helpers, disabled hooks/fsmonitor/credential helpers, and descriptor-pinned repository metadata.

The Home Assistant update contract remains unchanged: `/homeassistant` is not a Git worktree, secret/runtime exclusions remain intact, no blind `git pull` is permitted, and remote application remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**.
