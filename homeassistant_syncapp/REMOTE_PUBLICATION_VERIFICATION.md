# Authoritative post-push verification

A successful `git push` process exit is necessary but not sufficient for SyncApp to persist managed-path state. The managed remote branch must still identify the exact commit whose content was authorized for publication.

After pushing the immutable expected commit, SyncApp queries the configured `origin` with `git ls-remote --heads` for the exact managed branch. The response must contain exactly that branch and exactly the expected commit ID. If the branch is absent, malformed, or has already moved to a different commit, publication is treated as failed and managed-path manifest persistence does not proceed.

This deliberately fails closed when another writer advances the remote immediately after SyncApp's push. A later cycle can fetch and reconcile the actual remote state rather than recording local control state that falsely assumes the remote still points at SyncApp's commit.

Remote provenance validation remains mandatory before publication, and the push source remains the exact validated commit object rather than mutable `HEAD`.

Remote updates remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. No blind `git pull` touches `/homeassistant`, and secret/runtime exclusions remain unchanged.
