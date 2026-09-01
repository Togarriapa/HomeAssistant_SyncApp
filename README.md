# HomeAssistant SyncApp

A Home Assistant OS app that safely synchronizes Home Assistant configuration with a designated GitHub repository.

## Design goal

Availability comes before automatic convergence. Remote updates must never be pulled directly into the live Home Assistant configuration.

The intended remote-to-local workflow is:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

Local changes are filtered before they are committed so secrets, databases, logs, caches, generated files, and runtime state are not pushed accidentally.

> [!WARNING]
> This project is in early development and is not yet ready to manage a production Home Assistant instance.
