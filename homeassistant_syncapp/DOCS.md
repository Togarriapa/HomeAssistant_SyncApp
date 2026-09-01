# HomeAssistant SyncApp

## Current development milestone

Version `0.1.0` now implements the complete safety pipeline for an **experimental, explicitly enabled** remote apply:

- read the Home Assistant configuration from `/homeassistant`;
- exclude secrets, runtime state, databases, logs, caches, keys, certificates, and generated files;
- mirror allowed files into an isolated Git worktree under `/data`;
- commit and push local changes when `dry_run` is disabled;
- fetch and classify remote Git state as equal, local-ahead, remote-ahead, remote-only, or diverged;
- refuse pushes and applies when Git history is diverged;
- enumerate a remote commit as untrusted Git tree data before materializing it;
- reject blocked paths, symlinks/special Git modes, oversized files, and oversized trees;
- materialize accepted remote files only into `/data/staging`;
- syntax-check staged YAML/YML (including Home Assistant custom tags) and JSON;
- preserve the previous staging snapshot if a new candidate fails validation;
- refuse remote application if allowed live configuration has drifted from the local Git HEAD;
- create both a local rollback snapshot/journal and a synchronous Supervisor partial backup before mutation;
- copy or delete only policy-approved regular files using atomic replacement for writes;
- run the Supervisor Home Assistant configuration check after the recoverable file update and before restart;
- restart Home Assistant only after semantic validation succeeds;
- verify the Core API becomes healthy after restart;
- restore the prior files and, when required, restart/verify the prior configuration after a failed apply;
- recover an interrupted transaction before performing any new Git synchronization;
- re-fetch GitHub before adopting a successfully verified remote commit as the local baseline.

There is still **no direct `git pull` into `/homeassistant`**. Git checkout/reset operations only affect the isolated repository under `/data/repository`.

## Configuration

- `repository_url`: target GitHub configuration repository. This is separate from the repository containing SyncApp itself.
- `branch`: branch to synchronize, normally `main`.
- `github_token`: GitHub token used for authenticated Git operations. It is passed to Git through process environment configuration rather than being embedded in the remote URL.
- `poll_interval_seconds`: synchronization polling interval. Minimum 30 seconds.
- `dry_run`: defaults to `true`. No local push or remote live apply is performed while enabled.
- `remote_apply_enabled`: defaults to `false`. Remote live writes require this to be `true` **and** `dry_run` to be `false`.
- `verify_timeout_seconds`: maximum time to wait for Home Assistant Core to become healthy after a restart; default 120 seconds.
- `git_user_name` / `git_user_email`: identity used for automatically generated commits.

## Safety model

The remote-to-local workflow is:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

### Detect / Fetch

The app fetches into an isolated Git worktree. A diverged history is blocked. Before a remote update can touch live files, the allowed live Home Assistant configuration must still match the local Git HEAD. This deliberately conservative rule avoids silently overwriting local edits that have not yet been committed and pushed.

### Stage / Validate

The fetched remote tree is treated as untrusted input. Blocked paths such as `secrets.yaml`, `.storage`, databases, logs, caches, private-key material, symlinks, unsupported Git modes, and excessive content are rejected before staging. YAML and JSON syntax is checked in `/data/staging` without modifying live Home Assistant files.

Static validation is not treated as proof that Home Assistant accepts the configuration semantically.

### Backup / Apply

Before live mutation, SyncApp creates a local path-level rollback snapshot plus a persistent transaction journal under `/data/transaction`. It then requests a synchronous Supervisor partial backup of Home Assistant. If the Supervisor backup fails, live configuration files are not changed.

Only paths allowed by the same policy used for local-to-GitHub synchronization can be written or deleted. Existing symlink targets or symlinked parent directories are refused. Writes use a temporary sibling file followed by atomic replacement.

### Verify

After file application, SyncApp calls the Supervisor Core configuration check. If that fails, the prior files are restored without restarting the still-running old Core process.

If the check succeeds, SyncApp restarts Core and waits for its API health endpoint. Only after that succeeds does it re-fetch the configured Git branch, verify the remote commit did not move, adopt the verified commit in the isolated Git worktree, update the managed-file manifest, and remove the transaction snapshot.

### Rollback / crash recovery

If health verification fails after restart, the prior files are restored, checked, restarted, and health-verified. If rollback health itself cannot be proven, the transaction journal and snapshot are retained with a failure state rather than being discarded.

On every synchronization cycle, an unresolved transaction is handled before any new Git activity. The app fails closed: it attempts to restore and verify the previous configuration before continuing.

## Experimental status

The transaction logic has unit/failure-injection coverage and the app image is built in CI, but automated tests do not substitute for exercising backup, `/core/check`, restart, and Core-health behavior against a real Home Assistant OS/Supervisor installation. Keep `remote_apply_enabled: false` until the integration/canary milestone has been completed for the target environment.
