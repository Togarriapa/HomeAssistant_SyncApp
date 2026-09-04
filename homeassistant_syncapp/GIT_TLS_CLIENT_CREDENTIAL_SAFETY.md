# Git TLS client-credential safety

SyncApp supports a GitHub HTTPS repository and does not expose a trusted mutual-TLS client certificate option. Inherited runtime variables must therefore not be able to make Git/libcurl select arbitrary client certificate or private-key material.

Before constructing the synchronization engine, SyncApp removes:

- `GIT_SSL_CERT`
- `GIT_SSL_KEY`
- `GIT_SSL_CERT_PASSWORD_PROTECTED`
- `GIT_SSL_CERT_TYPE`
- `GIT_SSL_KEY_TYPE`
- `GIT_PROXY_SSL_CERT`
- `GIT_PROXY_SSL_KEY`
- `GIT_PROXY_SSL_CERT_PASSWORD_PROTECTED`

This prevents ambient add-on/container state from selecting certificate/key files, key formats such as OpenSSL engine-backed keys, or interactive password-protected certificate behavior.

## Deliberate trust boundary

CA trust inputs such as `GIT_SSL_CAINFO` and `GIT_SSL_CAPATH` are **not** removed by this milestone. Custom trust roots can be legitimate in environments with transparent TLS inspection, and SyncApp does not yet have an explicit trusted-CA configuration contract. Repository-local client-certificate configuration is likewise a separate control-plane boundary and is not claimed closed here.

Existing direct-proxy policy, TLS verification, default TLS version/cipher policy, and GitHub transport provenance protections remain unchanged.

The live update contract remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. `/homeassistant` remains outside Git, no blind `git pull` is used, and protected secret/runtime exclusions are unchanged.
