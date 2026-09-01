# Changelog

## 0.1.0

- Bootstrap the Home Assistant app structure.
- Add safe file filtering for local configuration capture.
- Add authenticated Git operations without embedding the token in the remote URL.
- Add local-to-GitHub synchronization with dry-run enabled by default.
- Detect remote divergence and refuse local pushes when the remote has advanced.
- Add Supervisor client primitives for later validation, backup, restart, and rollback work.
