# HomeAssistant SyncApp

A Home Assistant OS app that safely synchronizes Home Assistant configuration with a designated, separately configured GitHub repository.

## Repository separation

There are **two different repositories** in this design:

1. **SyncApp source repository** — `Togarriapa/HomeAssistant_SyncApp`. This contains the Home Assistant app/add-on code, tests, documentation, and CI. SyncApp does not use this repository as Home Assistant configuration storage.
2. **Home Assistant configuration repository** — configured by the user with `homeassistant_repository_url`. This is the repository SyncApp reads from and writes to for bidirectional Home Assistant configuration synchronization.

For example, the app can be installed from `Togarriapa/HomeAssistant_SyncApp` while `homeassistant_repository_url` points to a completely separate repository such as `https://github.com/example/my-home-assistant-config.git`.

SyncApp rejects configuration that points `homeassistant_repository_url` back at its own source repository. The older `repository_url` option is accepted only as a compatibility alias for existing experimental installations and should not be used for new configuration.

## Design goal

Availability comes before automatic convergence. Remote updates must never be pulled directly into the live Home Assistant configuration.

The remote-to-local workflow is:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

Remote Git data is staged outside `/homeassistant`, validated, and—only when explicitly enabled—applied through a journaled transaction with a Supervisor backup, Home Assistant configuration check, restart health verification, and rollback path. Live configuration drift blocks remote apply rather than being overwritten silently.

Local changes are filtered and validated before they are committed to the configured Home Assistant repository so secrets, databases, logs, caches, generated files, private-key material, and runtime state are not pushed accidentally. The same blocked-file policy is enforced for remote application.

Remote live application is disabled by default: `dry_run` defaults to `true` and `remote_apply_enabled` defaults to `false`.

> [!WARNING]
> This project is in early development and is not yet ready to manage a production Home Assistant instance. The transaction path has automated failure-injection coverage, but it still requires canary testing against a real Home Assistant OS/Supervisor installation before production use.
