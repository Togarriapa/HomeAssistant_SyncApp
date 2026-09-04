# Remote deletion safety budget

A remote Home Assistant configuration can be syntactically valid, pass Supervisor `/core/check`, and still be operationally destructive if it removes a large portion of the managed configuration. A mistaken commit or compromised managed repository could therefore converge Home Assistant to a drastically reduced but technically valid configuration.

SyncApp applies a fail-closed deletion budget before any Supervisor backup is requested and before a transaction directory or live mutation is created.

## Defaults

- `remote_max_deletions: 25`
- `remote_max_deletion_percent: 50`

A remote candidate is rejected when **either** limit is exceeded.

The percentage denominator is the current policy-approved baseline used by that operation:

- ordinary remote apply: policy-approved files at the current managed Git HEAD;
- remote-authoritative first bootstrap: policy-approved live Home Assistant files.

The threshold comparison is inclusive. For example, deleting exactly 50% of a baseline is allowed by the default percentage budget; deleting more than 50% is blocked.

## Operator control

Set `remote_max_deletions: 0` to reject every remote deletion. Set `remote_max_deletion_percent: 0` for the same effect when the baseline is non-empty.

A deliberate large deletion requires increasing both limits sufficiently. Changing these settings only changes the pre-transaction destructive-change gate; it does not bypass staging validation, Supervisor backup, `/core/check`, restart/health verification, exact Git adoption, drift protection, transaction journaling, rollback, or blocked-file policy.

## Safety boundary

The budget applies only to policy-approved managed paths. `secrets.yaml`, `.storage`, databases, logs, caches, private-key material, generated/runtime state, and other blocked paths never become eligible merely because a deletion budget is increased.

Rejected candidates remain staged outside `/homeassistant` for diagnosis, but SyncApp does not create a live transaction or call Supervisor for them.

The required remote workflow remains:

**Detect → Fetch → Stage → Validate → destructive-change gate → Backup → Apply → Verify → Rollback if necessary**

The destructive-change gate is part of validation and does not replace any transaction safety step.
