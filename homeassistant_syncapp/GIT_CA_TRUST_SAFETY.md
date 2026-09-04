# Git CA trust safety

SyncApp now has an explicit trust model for GitHub HTTPS certificate authorities instead of allowing `.git/config` or inherited runtime state to select arbitrary CA files and directories.

## Default trust

The app image explicitly installs and verifies the Alpine system CA store. Before the synchronization engine starts, SyncApp sets:

- `GIT_SSL_CAINFO=/etc/ssl/certs/ca-certificates.crt`
- `GIT_SSL_CAPATH=/etc/ssl/certs`

Those Git environment variables override repository-local `http.sslCAInfo` / `http.sslCAPath` values. Ambient `CURL_CA_BUNDLE`, `SSL_CERT_FILE`, and `SSL_CERT_DIR` inputs are removed so the image trust store remains authoritative.

## Optional trusted extra bundle

Deployments that need an additional CA may configure `git_ca_bundle` with a **single filename** stored in SyncApp's own app-configuration directory. Home Assistant mounts only that per-app `addon_config` directory read-only at `/config`; SyncApp does not request broad access to Home Assistant's global `/ssl` directory.

The custom file is:

1. opened with no-follow semantics;
2. required to be a regular, non-empty file no larger than 2 MiB;
3. read from the opened descriptor;
4. atomically copied to a mode-`0600` snapshot under `/data`;
5. supplied to Git through authoritative `GIT_SSL_CAINFO` while the normal system CA directory remains configured through `GIT_SSL_CAPATH`.

This prevents a path swap after validation from changing the CA bytes Git consumes during the running app instance.

The setting is intentionally a filename rather than an arbitrary path: absolute paths, traversal, and nested paths are rejected.

TLS peer verification remains enabled, TLS version/cipher negotiation remains locked to libcurl defaults, proxy routing remains direct-only, and ambient client-certificate/private-key selectors remain disabled.

The live update contract remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. `/homeassistant` remains outside Git, no blind `git pull` is used, and secret/runtime exclusions are unchanged.
