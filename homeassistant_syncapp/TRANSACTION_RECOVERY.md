# Transaction recovery evidence

SyncApp treats `/data/transaction` as safety-critical persistent state. Automatic recovery may restore or delete policy-approved live Home Assistant files, so recovery evidence must be proven trustworthy before any rollback or post-verification finalization decision is made.

## Journal versions

New transactions write journal version `2`. Version 2 adds `integrity_sha256`, a SHA-256 checksum over a canonical JSON representation of every journal field except the checksum itself. The checksum is an accidental-corruption detector, not a cryptographic authentication mechanism.

Structurally valid version `1` journals remain readable so an upgrade does not strand a transaction created by an earlier experimental build. Version 1 receives the same field, path, state, and snapshot consistency checks as version 2.

## Fail-closed validation

Before SyncApp interprets a recovery state it validates that:

- the journal is a JSON object with a supported version and known transaction state;
- the referenced commit is a syntactically valid Git object identifier;
- write, delete, and `existed` entries are unique policy-approved relative paths;
- write and delete sets do not overlap and the apply plan is not empty;
- staged-content SHA-256 entries are syntactically valid and refer only to write paths;
- `existed` is a subset of the transaction's affected paths;
- any recorded Supervisor backup slug is syntactically safe;
- version 2 integrity metadata matches the exact journal payload.

After preparation has completed, SyncApp also enumerates the rollback snapshot without following symlinks and requires its regular-file set to match the journal's `existed` set exactly. This is important because `existed` controls rollback semantics: a path marked as previously existing is restored from the snapshot, while an affected path that did not previously exist is deleted during rollback.

If that relationship cannot be proven, SyncApp must not guess. The live configuration, transaction journal, and snapshot remain in place and the synchronization cycle fails closed for operator investigation.

The `preparing` state is the one exception to the exact snapshot-set check because a crash may occur while the snapshot itself is still being constructed. Recovery from `preparing` is discard-only: live mutation has not begun.

## Relationship to the remote-update workflow

Journal validation does not replace any stage of the remote-update safety pipeline. It protects the recovery boundary around the same required workflow:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No recovery path performs a Git checkout or pull into `/homeassistant`. Secret/runtime-file exclusions are re-applied to journal and snapshot paths, so corrupt persistent state cannot authorize `secrets.yaml`, `.storage`, databases, logs, keys, certificates, traversal paths, or other blocked content for rollback mutation.

## Operator response to corruption

Do not delete ambiguous transaction evidence merely to make SyncApp start synchronizing again. Preserve `/data/transaction` and the corresponding Supervisor backup until the live configuration and intended Git baseline have been independently inspected. On an important installation, keep automatic remote apply disabled until the cause of the corruption is understood.
