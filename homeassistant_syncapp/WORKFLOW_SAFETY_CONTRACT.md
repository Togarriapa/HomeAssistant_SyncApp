# Remote update safety contract

SyncApp treats the Home Assistant configuration tree as a protected live filesystem, not as a Git working tree.

The required remote-update sequence is:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

This ordering is a safety boundary, not an implementation detail.

## Non-negotiable invariants

- Git may fetch and inspect remote history in the managed repository under `/data`, but SyncApp must never use a blind `git pull` to update live Home Assistant configuration.
- Modules that mutate or verify `/homeassistant` (`apply.py`, `transaction.py`, and `live_fs.py`) must not shell out to Git. Live changes are performed only by the validated transaction layer.
- `secrets.yaml` / `secrets.yml`, `.storage`, databases, logs, PID/lock/temp files, private-key/certificate material, `.git`, and other runtime state remain outside the managed path policy.
- A remote candidate is not eligible for live mutation until fetched bytes have been staged and validated and a Supervisor pre-apply backup has been created and verified.
- Failed validation, failed backup evidence, failed apply verification, or interrupted transactions must fail closed and preserve or restore recovery evidence as appropriate.

## CI regression guard

`tests/test_workflow_safety_contract.py` intentionally checks architecture-level properties in addition to behavior-level transaction tests:

1. `git_repo.py` must not introduce a `pull` Git subcommand.
2. live mutation modules must remain independent of `subprocess`/Git execution.
3. representative secret/runtime paths must remain rejected by `is_allowed_relative()`.
4. primary documentation must continue to state the required update ordering.

The guard is deliberately conservative. If a future design genuinely needs to change one of these properties, the change should be reviewed as a safety-boundary redesign rather than bypassing the test.
