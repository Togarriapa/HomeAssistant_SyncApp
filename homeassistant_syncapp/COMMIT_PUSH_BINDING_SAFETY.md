# Validated commit-to-push binding

Git commits the staged index, so validation cannot stop at the worktree or even at a pre-commit index snapshot. SyncApp therefore verifies the immutable commit object created for a local publication before any network push.

After descriptor-based worktree validation, staged-index binding, live-source continuity checks, and Home Assistant semantic validation all succeed, SyncApp creates its local commit. It then enumerates the exact commit tree with Git plumbing, requires only policy-approved regular blobs with supported modes, hashes the committed blob bytes with SHA-256, and requires that path/content manifest to exactly equal the fully validated candidate manifest.

If the commit differs, SyncApp does not push. The suspect commit is intentionally left local rather than being silently rewritten or reset. The unpushed-commit recovery path independently refuses to send it unless that immutable commit can later be revalidated against descriptor-validated live Home Assistant configuration and semantic validation.

This closes the final index-to-commit handoff without modifying live configuration. Remote updates remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. No blind `git pull` touches `/homeassistant`, and secret/runtime exclusions remain unchanged.
