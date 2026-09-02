# Validated staging byte integrity

Remote Git content is materialized under SyncApp's isolated staging directory, never directly into `/homeassistant`. Static validation is only meaningful if the exact bytes that passed validation are the bytes later used to decide whether a remote update is a no-op and, for mutating updates, the bytes that enter the backed-up transaction.

SyncApp therefore binds a staged remote candidate to a per-file SHA-256 manifest at Stage/Validate time. Each policy-approved file is read once into memory, size-bounded, syntax-validated from that exact byte buffer, and hashed from the same buffer. The resulting `StagingResult` records the complete path/hash set, file count, total bytes, and an explicit integrity-bound marker. An empty remote tree is also explicitly bound so that adding a file later is detectable.

Immediately before remote apply planning, SyncApp re-runs static directory validation and requires the complete path/hash/count/size result to match the validated staging result. Failure happens before deletion budgeting, no-op adoption, Supervisor backup creation, transaction creation, Git adoption, managed-manifest persistence, or `/homeassistant` mutation.

This specifically closes the window where a valid staged file could be replaced by different-but-still-valid YAML/JSON/Python after validation. Re-running only syntax validation would not detect that substitution; the cryptographic manifest does.

For mutating candidates, this is only the first continuity layer. `FileTransaction.prepare()` independently pins the staged write bytes again, and the transaction rechecks those hashes after the Supervisor backup window immediately before live mutation. The continuity chain is therefore:

**Stage exact Git bytes → static Validate + hash → pre-apply static/hash revalidation → transaction hash pin → Backup → pre-Apply hash recheck → Apply → Verify → Rollback if necessary**

The normal synchronization policy remains unchanged. `secrets.yaml`, `.storage`, databases, logs, keys/certificates, temporary files, and other blocked runtime paths never become part of the staged validation manifest.

This mechanism does not make the staging directory trusted storage. It deliberately treats staging as mutable evidence and re-proves it at each transition that matters. It also does not introduce any Git checkout or pull into `/homeassistant`.
