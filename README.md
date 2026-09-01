# HomeAssistant SyncApp

A Home Assistant OS app that safely synchronizes Home Assistant configuration with a separately configured GitHub repository.

## Repository separation

SyncApp deliberately has two different repository roles:

1. **SyncApp source repository** — `Togarriapa/HomeAssistant_SyncApp`. This contains the add-on implementation, tests, CI, and documentation. Home Assistant's add-on metadata points here as the project/source URL.
2. **Managed Home Assistant repository** — configured with `homeassistant_repository_url`. This is the repository SyncApp clones under `/data/repository` and reads/writes for Home Assistant configuration synchronization.

For example, the app may be installed from `Togarriapa/HomeAssistant_SyncApp` while `homeassistant_repository_url` is `https://github.com/example/my-home-assistant-config.git`.

SyncApp rejects using its own source repository as the managed Home Assistant target. The old `repository_url` setting is accepted only as a deprecated upgrade alias; when both old and new values are present they must identify the same GitHub repository or startup fails closed.

An existing `/data/repository` is bound to both its approved remote identity and its persistent branch. SyncApp verifies the effective `origin` fetch URL, every effective `origin` push URL, and the checked-out branch before reuse, and repeats remote provenance validation immediately before every fetch and push. This prevents a tampered Git `pushurl`, an implicit repository retarget, or a silent branch switch from reusing managed-path/transaction state against a different destination or history. See `homeassistant_syncapp/REPOSITORY_PROVENANCE.md` for the full contract.

## Design goal

Availability comes before automatic convergence. Remote updates must never be pulled directly into the live Home Assistant configuration.

The remote-to-local workflow is:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

Remote Git data is staged outside `/homeassistant`, validated, and—only when explicitly enabled—applied through a journaled transaction with a Supervisor backup, Home Assistant configuration check, restart health verification, and rollback path. Live configuration drift blocks ordinary remote apply rather than being overwritten silently.

Before a staged remote candidate can enter the Backup/Apply transaction, SyncApp also enforces a destructive-deletion budget. By default, a candidate is rejected if it deletes more than 25 policy-approved files or more than 50% of the current managed baseline. This prevents a mistaken or compromised but syntactically valid remote commit from silently converging Home Assistant to a drastically reduced configuration. See `homeassistant_syncapp/REMOTE_DELETION_SAFETY.md`.

A fresh SyncApp instance connected to an already-populated configuration repository fails closed until initial authority is selected explicitly. See `homeassistant_syncapp/BOOTSTRAP.md` for the local-authoritative and remote-authoritative first-sync contracts. Remote-authoritative bootstrap uses the same staged, backed-up, verified transaction machinery; it does not disable ordinary drift protection globally, and its policy-approved live baseline is subject to the same remote-deletion budget.

Local changes are filtered before they are committed to the configured managed Home Assistant repository so secrets, databases, logs, caches, generated files, private-key material, and runtime state are not pushed accidentally. The same blocked-file policy is enforced for remote application and first-run bootstrap.

The persisted managed-path manifest under `/data` is treated as safety-critical state, not a best-effort cache. If it is malformed, has the wrong JSON shape, or names a blocked/absolute/traversal path, synchronization fails closed before local mirroring. Managed paths are revalidated immediately before deletion so damaged state cannot turn the isolated repository cleanup path into a filesystem traversal.

After a remote configuration has passed Core health verification and the exact commit has been adopted in the isolated managed repository, later bookkeeping failures preserve the verified live state and recovery journal. SyncApp proves Git/live consistency on the next cycle before finalizing; it does not roll live files behind an already-adopted Git baseline.

Remote live application is disabled by default: `dry_run` defaults to `true` and `remote_apply_enabled` defaults to `false`. Both first-sync authority flags also default to `false`.

> [!WARNING]
> This project is in early development and is not yet ready to manage a production Home Assistant instance. The transaction path has automated failure-injection coverage, but it still requires canary testing against a real Home Assistant OS/Supervisor installation before production use.
