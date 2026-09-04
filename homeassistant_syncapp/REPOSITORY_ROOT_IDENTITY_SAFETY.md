# Managed repository root identity safety

The isolated Git checkout under `/data` is persistent control state. Validating that its pathname is a real directory is not sufficient if a later Git subprocess reopens that pathname after it has been renamed or replaced.

SyncApp therefore binds each `GitRepository` instance to the device/inode identity of the first safely opened repository root. Normal Git commands open the root with `O_DIRECTORY | O_NOFOLLOW`, require that identity to remain the one previously bound to the repository object, and launch Git from `/proc/self/fd/<fd>` while explicitly inheriting that directory descriptor. A pathname swap after the descriptor is opened cannot redirect the subprocess into the replacement tree.

After every Git subprocess, SyncApp proves that the configured repository pathname still identifies the exact opened directory. Replacement during a command therefore fails closed even if Git itself succeeded against the detached original tree. Replacement between commands is rejected before the next subprocess is started.

This boundary is intentionally Linux-specific because the Home Assistant add-on runtime and CI target Linux and `/proc/self/fd` provides the required descriptor-to-working-directory binding. Custom explicit `cwd` calls remain outside this helper; production managed-repository operations use the pinned default repository root.

This protection composes with configured-URL Fetch/publication provenance and fail-closed bootstrap. It does not make `/homeassistant` a Git working tree and does not change the live update sequence: **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. Secret/runtime exclusions remain unchanged.
