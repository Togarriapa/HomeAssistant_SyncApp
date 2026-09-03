# Publication network-target binding

SyncApp persists the configured repository URL as the authority for outbound publication. The persistent Git checkout under `/data` is still checked to ensure its `origin` fetch and push URLs match that configured authority, but a successful provenance check must not authorize a later mutable `origin` lookup for the actual network operation.

Publication therefore sends the exact validated commit directly to `settings.repository_url`, and the authoritative post-push `ls-remote` verification queries that same configured URL directly. A concurrent or malicious retarget of `.git/config` after provenance validation cannot redirect the push or its verification query.

The persistent `origin` remains useful for fetch/tracking state and is revalidated on subsequent cycles. If it has been retargeted, normal repository setup fails closed rather than silently adopting the new destination.

This boundary composes with the exact commit-to-push binding and post-push remote-head verification. Remote updates remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. No blind `git pull` touches `/homeassistant`, and secret/runtime exclusions remain unchanged.
