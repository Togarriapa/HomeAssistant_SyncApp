# Fetch network-target binding

SyncApp treats the configured repository URL as the authority for inbound Git network operations. Persistent `origin` configuration under `/data` is still validated before every fetch, but a successful provenance check does not authorize a later mutable `origin` lookup as the actual network target.

Fetch first queries the exact managed branch at `settings.repository_url`. If the branch exists, SyncApp fetches only that branch from the configured URL into `refs/remotes/origin/<branch>`. If the branch is authoritatively absent, SyncApp deletes only that managed tracking ref rather than depending on named-remote pruning behavior.

After either path, SyncApp queries the configured URL again and requires local tracking state to match the authoritative branch state exactly. A concurrent branch move therefore fails closed instead of allowing stale tracking evidence to drive Detect/Stage decisions. A concurrent `.git/config` retarget after provenance validation cannot redirect the fetch because the network operation never names `origin`.

The persistent `origin` entry is not silently rewritten. A retarget remains visible and is rejected by the next provenance check.

This strengthens the **Fetch** phase while preserving **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. No Git operation targets `/homeassistant`, no blind `git pull` is introduced, and secret/runtime exclusions remain unchanged.
