# Git HTTP concurrency safety

Git allows HTTP request parallelism to be configured through `http.maxRequests`, and the `GIT_HTTP_MAX_REQUESTS` environment variable overrides that repository setting. Git's documented default is five parallel requests.

SyncApp fixes `GIT_HTTP_MAX_REQUESTS=5` before constructing the synchronization engine. This preserves normal Git behavior while preventing inherited runtime state or persistent repository-local Git configuration from amplifying outbound HTTP concurrency and associated socket/memory pressure.

This is a resource-safety boundary only. It does not change repository provenance, authentication, proxy policy, CA trust, TLS verification, staged content, or the remote-update transaction.

The live update contract remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. `/homeassistant` remains outside Git, no blind `git pull` is used, and secret/runtime exclusions are unchanged.
