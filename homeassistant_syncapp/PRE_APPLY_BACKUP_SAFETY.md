# Pre-apply Supervisor backup safety

Remote live mutation is permitted only after SyncApp has created and independently verified a synchronous Supervisor partial Home Assistant backup.

The required remote-update order remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

## Backup proof before mutation

For every mutating remote transaction, SyncApp requests a partial backup with:

- `homeassistant: true`;
- `homeassistant_exclude_database: true`;
- `background: false`;
- a deterministic `SyncApp pre-apply <commit>` name.

A returned backup slug is not sufficient evidence. Before the transaction journal may enter `backed_up`, SyncApp requires Supervisor to prove all of the following:

1. backup inventory contains exactly one entry with the returned slug;
2. the inventory name exactly matches the request;
3. the inventory type is `partial`;
4. inventory `content.homeassistant` is `true`;
5. inventory reports a finite, positive backup size;
6. `/backups/<slug>/info` returns the same slug, name, and type;
7. the detail record contains a non-empty Home Assistant version;
8. the detail record confirms `homeassistant_exclude_database: true`;
9. detail metadata reports a finite, positive backup size equal to the inventory size after numeric normalization.

Supervisor currently documents inventory size as a number and backup-detail size as an MB string. SyncApp therefore normalizes both as decimal values rather than depending on representation or formatting such as `12.5` versus `"12.50"`. Boolean, malformed, NaN/infinite, zero, negative, missing, or cross-endpoint-mismatched values fail closed.

If any proof is missing or inconsistent, the transaction is discarded while still in the pre-mutation phase. Live Home Assistant configuration is left untouched, `/core/check` is not invoked for the candidate, and Core is not restarted.

The size proof is evidence that Supervisor has materialized a non-empty backup object consistently across its inventory/detail views. It is not a claim that every archive member has been decompressed or restored successfully; actual archive/storage behavior remains part of the disposable-HAOS acceptance work.

## Continuity across the mutation boundary

Initial verification is not treated as a permanent lease on the backup. After the potentially long backup window has closed and live/staged drift checks pass, SyncApp re-runs the complete Supervisor backup proof immediately before `FileTransaction.apply()`.

The same backup is then proved a third time immediately after descriptor-relative file application and before the candidate `/core/check` or Core restart. The non-zero, cross-endpoint size proof is part of each of these checks.

These gates intentionally produce different failure behavior:

- if the pre-mutation continuity proof fails, transaction state is discarded and `/homeassistant` remains untouched;
- if the post-apply continuity proof fails, SyncApp restores the local rollback snapshot immediately while the old Core process is still running, then aborts without candidate `/core/check` or restart.

This does not make an external Supervisor backup impossible to remove concurrently. It narrows the unobserved interval around the first live mutation and refuses to proceed when the last-resort backup layer cannot still be proved at either side of that boundary. The independently pinned local rollback snapshot remains the primary automatic rollback mechanism.

## Journal boundary

`FileTransaction.apply()` accepts only a transaction in the `backed_up` state. The production transaction runner records that state only after the initial Supervisor backup proof succeeds, and it still requires the continuity proof immediately before invoking `apply()`.

This keeps crash recovery conservative: a journal cannot claim the safety boundary was crossed merely because a backup-create endpoint returned an identifier.

## Canary alignment

The disposable-HAOS canary exercises the backup identity/content inventory/detail fields, while the full production transaction additionally enforces the non-zero cross-endpoint size proof on every backup verification. Issue #4 must therefore retain the real full-transaction exercise; the lightweight canary is not a substitute for production-path verification.

A real HAOS/Supervisor compatibility failure must be investigated; the application should not weaken this proof merely to make an unsupported runtime pass.

## Scope

This mechanism does not restore, delete, or prune a backup. Existing post-success backup-retention rules remain separate and run only after successful transaction completion.

Secret/runtime exclusions are unchanged. No Git checkout, reset, or pull operates against `/homeassistant`; Git remains isolated under `/data/repository` and staged data under `/data/staging`.
