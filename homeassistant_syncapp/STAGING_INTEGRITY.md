# Validated staging byte integrity

Remote Git content is materialized under SyncApp's isolated staging directory, never directly into `/homeassistant`. Static validation is only meaningful if the exact fetched Git bytes are the bytes that pass validation and are later used to decide whether a remote update is a no-op and, for mutating updates, the bytes that enter the backed-up transaction.

SyncApp therefore binds both sides of Stage/Validate. Each fetched Git blob is size-checked and SHA-256 hashed from the exact `read_blob()` byte buffer before it is written. After materialization, each policy-approved staged file is read into memory, size-bounded, syntax-validated from that exact byte buffer, and hashed from the same buffer. The complete materialized path/hash manifest must exactly equal the fetched-Git path/hash manifest before the staging tree can replace the previous staging directory.

## Filesystem confinement during materialization

Byte identity is not enough if an attacker-controlled pathname can redirect where fetched bytes are written. During materialization SyncApp therefore opens the newly created staging root with `O_DIRECTORY|O_NOFOLLOW` and keeps that descriptor open. Every nested parent is opened or created relative to an already-open descriptor; symlink/non-directory parents are refused. New leaves are created relative to the opened parent with `O_EXCL|O_NOFOLLOW`, written through the file descriptor, and both the file and parent directory are fsynced.

The opened staging root's device/inode identity is recorded. SyncApp verifies that the expected pathname still identifies that same opened tree before and after static validation, before installation, and under the final staging pathname after rename. A root pathname rename or symlink replacement therefore cannot redirect fetched Git bytes: descriptor-relative writes remain bound to the directory that was actually opened, and the identity mismatch makes staging fail closed rather than trusting the substituted pathname.

If confinement itself reports that a staging pathname was replaced, that pathname is not treated as trusted cleanup evidence. The previous validated staging tree remains authoritative and the suspicious temporary evidence may require inspection/removal before another attempt.

The resulting `StagingResult` records the complete path/hash set, file count, total bytes, and an explicit integrity-bound marker. An empty remote tree is also explicitly bound so that adding a file later is detectable.

Immediately before remote apply planning, SyncApp re-runs static directory validation and requires the complete path/hash/count/size result to match the validated staging result. Failure happens before deletion budgeting, no-op adoption, Supervisor backup creation, transaction creation, Git adoption, managed-manifest persistence, or `/homeassistant` mutation.

## Apply-plan semantics are bound to validated evidence

After that revalidation, SyncApp does **not** rediscover remote intent by walking the mutable staging directory again. For integrity-bound remote candidates, the validated `StagingResult` path/hash manifest is the authority for the desired path set, live/hash comparisons, and deletion decisions. A managed path becomes a delete only when it is absent from the validated remote manifest—not because a staged pathname later disappeared, became a symlink, or was otherwise damaged.

This distinction prevents a post-validation staging race from turning a validated remote file into an unintended live deletion. If live already equals a validated desired hash, a later loss of the staged copy cannot manufacture a deletion and the update may remain a true no-op. If live needs a write, the staged source must still exist and `FileTransaction.prepare()` must pin exactly the validated hash before any Supervisor Backup is requested. A different same-size source causes the prepared local transaction evidence to be discarded before Backup or live mutation.

This closes several related substitution windows: different bytes cannot be substituted between fetched Git blob materialization and static validation; a valid staged file cannot later be replaced by different-but-still-valid YAML/JSON/Python after validation; and staging damage after the integrity check cannot alter the validated desired/deletion semantics. Re-running only syntax validation would not provide these guarantees.

For mutating candidates, transaction pinning remains another independent continuity layer. The transaction rechecks its pinned staged hashes after the Supervisor backup window immediately before live mutation. The continuity chain is therefore:

**Fetch exact Git blob bytes → hash → descriptor-confined Stage → static Validate + hash → require Git/staging hash equality → pre-apply static/hash revalidation → build desired/deletion plan from validated manifest → transaction hash pin must equal validated hash → Backup → pre-Apply hash recheck → Apply → Verify → Rollback if necessary**

The normal synchronization policy remains unchanged. `secrets.yaml`, `.storage`, databases, logs, keys/certificates, temporary files, and other blocked runtime paths never become part of the staged validation manifest.

This mechanism does not make the staging directory trusted storage. It deliberately treats staging as mutable evidence and uses immutable validation evidence for decisions whenever possible. It also does not introduce any Git checkout or pull into `/homeassistant`.
