# Local publication validation continuity

SyncApp must not publish an isolated Git candidate merely because that candidate passed static validation while Home Assistant happened to validate a different live configuration.

For a local publication with staged Git changes, the candidate is statically validated first. The live Home Assistant configuration is then independently descriptor-validated and its allowed path/hash manifest must exactly equal the isolated candidate manifest before the Supervisor semantic check starts.

After `check_core_configuration()` returns successfully, SyncApp descriptor-validates the live tree again. The post-check live manifest must still exactly equal the candidate. A persistent edit, replacement, add, or removal during the semantic-validation window therefore aborts local publication, discards isolated worktree changes, and performs no commit or push.

This continuity check is intentionally fail closed. It does not modify live configuration and does not attempt to overwrite a concurrent local edit.

Remote updates are unaffected and remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. No blind `git pull` is permitted against `/homeassistant`, and all existing secret/runtime exclusions remain unchanged.
