# Git TLS negotiation safety

SyncApp requires certificate verification for GitHub HTTPS transport. Repository-local or inherited Git settings must also not be able to select a legacy/custom TLS protocol version or cipher policy without an explicit SyncApp trust decision.

At startup SyncApp sets:

- `GIT_SSL_VERSION=`
- `GIT_SSL_CIPHER_LIST=`

Git documents the empty values for these variables as a request to use libcurl's default SSL/TLS version and cipher list, overriding explicit `http.sslVersion` and `http.sslCipherList` configuration. This prevents persistent `.git/config` or inherited runtime values from silently weakening or otherwise changing TLS negotiation policy.

This milestone intentionally does **not** modify CA roots, CA paths, client certificates, private keys, or certificate pinning. Those settings have legitimate deployment compatibility implications and require a separate explicit trust model before SyncApp constrains them.

The existing `http.sslVerify=true` and `http.proxySSLVerify=true` command-scope protections remain in force.

The live update contract remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. `/homeassistant` remains outside Git, no blind `git pull` is used, and secret/runtime exclusions are unchanged.
