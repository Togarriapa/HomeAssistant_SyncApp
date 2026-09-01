# HomeAssistant SyncApp

A Home Assistant OS app that safely synchronizes Home Assistant configuration with a designated GitHub repository.

## Design goal

Availability comes before automatic convergence. Remote updates must never be pulled directly into the live Home Assistant configuration.

The remote-to-local workflow is:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

Remote Git data is staged outside `/homeassistant`, validated, and—only when explicitly enabled—applied through a journaled transaction with a Supervisor backup, Home Assistant configuration check, restart health verification, and rollback path. Live configuration drift blocks remote apply rather than being overwritten silently.

Local changes are filtered before they are committed so secrets, databases, logs, caches, generated files, private-key material, and runtime state are not pushed accidentally. The same blocked-file policy is enforced for remote application.

Remote live application is disabled by default: `dry_run` defaults to `true` and `remote_apply_enabled` defaults to `false`.

> [!WARNING]
> This project is in early development and is not yet ready to manage a production Home Assistant instance. The transaction path has automated failure-injection coverage, but it still requires canary testing against a real Home Assistant OS/Supervisor installation before production use.
