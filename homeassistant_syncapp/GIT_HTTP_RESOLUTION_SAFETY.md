# Git HTTP hostname-resolution safety

SyncApp treats the configured HTTPS GitHub repository as the authoritative transport target. Repository-local Git configuration must not be able to provide libcurl with an alternate IP address for that hostname.

Every SyncApp Git subprocess therefore installs an empty command-scope `http.curloptResolve` value. Git documents an empty value as resetting inherited hostname-resolution entries to the empty list.

This prevents persistent `.git/config` from supplying repository-controlled DNS overrides while preserving normal system name resolution and the existing configured GitHub transport.

This control composes with the existing safeguards for TLS verification, HTTP redirects, extra headers, cookies, proxy/helper execution, inherited trace state, authoritative URL rewrite locking, and descriptor-pinned Git metadata.

The live Home Assistant workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and managed secret/runtime exclusions are unchanged.
