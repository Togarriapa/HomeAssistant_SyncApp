# Git HTTP cookie safety

SyncApp does not require persistent HTTP cookies to authenticate to or synchronize the configured GitHub repository. Repository-local Git configuration must therefore not be able to make SyncApp read an arbitrary cookie file or persist server cookies to disk.

Every SyncApp Git subprocess forces:

```text
http.cookieFile=
http.saveCookies=false
```

Git documents an empty `http.cookieFile` as avoiding a cookie file while still allowing connection-local cookies, and `http.saveCookies=false` prevents persistence. This removes repository-controlled cookie-file reads and writes without changing the configured GitHub token flow.

This control is additive to the existing safeguards for TLS verification, redirect policy, extra-header reset, proxy-command execution, credential/askpass/SSH helpers, transport URL rewrite locking, and descriptor-pinned Git metadata.

The live Home Assistant workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and managed secret/runtime exclusions are unchanged.
