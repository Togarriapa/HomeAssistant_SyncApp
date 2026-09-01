# HomeAssistant SyncApp

A Home Assistant OS app that safely synchronizes Home Assistant configuration with a designated GitHub repository.

## Design goal

Availability comes before automatic convergence. Remote updates must never be pulled directly into the live Home Assistant configuration.

The remote-to-local workflow is:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

Remote Git data is staged outside `/homeassistant`, validated, and—only when explicitly enabled—applied through a journaled transaction with a Supervisor backup, Home Assistant configuration check, restart health verification, and rollback path. Live configuration drift blocks ordinary remote apply rather than being overwritten silently.

A fresh SyncApp instance connected to an already-populated configuration repository fails closed until initial authority is selected explicitly. See `homeassistant_syncapp/BOOTSTRAP.md` for the local-authoritative and remote-authoritative first-sync contracts. Remote-authoritative bootstrap uses the same staged, backed-up, verified transaction machinery; it does not disable ordinary drift protection globally.

Local changes are filtered before they are committed so secrets, databases, logs, caches, generated files, private-key material, and runtime state are not pushed accidentally. The same blocked-file policy is enforced for remote application and first-run bootstrap.

Remote live application is disabled by default: `dry_run` defaults to `true` and `remote_apply_enabled` defaults to `false`. Both first-sync authority flags also default to `false`.

> [!WARNING]
> This project is in early development and is not yet ready to manage a production Home Assistant instance. The transaction path has automated failure-injection coverage, but it still requires canary testing against a real Home Assistant OS/Supervisor installation before production use.
