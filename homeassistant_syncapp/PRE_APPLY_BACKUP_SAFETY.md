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
5. `/backups/<slug>/info` returns the same slug, name, and type;
6. the detail record contains a non-empty Home Assistant version;
7. the detail record confirms `homeassistant_exclude_database: true`.

If any proof is missing or inconsistent, the transaction is discarded while still in the pre-mutation phase. Live Home Assistant configuration is left untouched, `/core/check` is not invoked for the candidate, and Core is not restarted.

## Journal boundary

`FileTransaction.apply()` accepts only a transaction in the `backed_up` state. The production transaction runner now records that state only after the Supervisor backup proof above succeeds.

This keeps crash recovery conservative: a journal cannot claim the safety boundary was crossed merely because a backup-create endpoint returned an identifier.

## Canary alignment

The disposable-HAOS canary exercises the same Supervisor inventory/detail fields so issue #4 can verify that the real Supervisor version exposes the evidence expected by production remote apply.

A real HAOS/Supervisor compatibility failure must be investigated; the application should not weaken this proof merely to make an unsupported runtime pass.

## Scope

This mechanism does not restore, delete, or prune a backup. Existing post-success backup-retention rules remain separate and run only after successful transaction completion.

Secret/runtime exclusions are unchanged. No Git checkout, reset, or pull operates against `/homeassistant`; Git remains isolated under `/data/repository` and staged data under `/data/staging`.
