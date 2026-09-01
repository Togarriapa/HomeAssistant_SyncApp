# HomeAssistant SyncApp

## Repository roles

SyncApp deliberately uses two separate GitHub repositories:

- **App source repository:** `Togarriapa/HomeAssistant_SyncApp`. This contains the Home Assistant app/add-on implementation, tests, CI, and documentation. The `url` field in `config.yaml` refers to this repository because Home Assistant uses it as the app project URL.
- **Managed Home Assistant repository:** configured with `homeassistant_repository_url`. This is the only repository SyncApp clones into `/data/repository` and uses for bidirectional Home Assistant configuration synchronization.

`homeassistant_repository_url` must be a GitHub HTTPS repository URL and must not point back to `Togarriapa/HomeAssistant_SyncApp`. The previous experimental option name `repository_url` remains accepted as a deprecated compatibility alias. If both values are present they must resolve to the same GitHub repository; otherwise SyncApp refuses to start rather than guessing which target is authoritative.

Example:

```yaml
homeassistant_repository_url: https://github.com/example/my-home-assistant-config.git
branch: main
dry_run: true
remote_apply_enabled: false
```

The GitHub token, when required, must grant the permissions needed on the **managed Home Assistant repository**, not on the SyncApp source repository.

## Current development milestone

Version `0.2.0` implements the complete safety pipeline for an **experimental, explicitly enabled** remote apply:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

The app:

- reads Home Assistant configuration from `/homeassistant`;
- excludes secrets, runtime state, databases, logs, caches, keys, certificates, and generated files;
- mirrors allowed files only into the isolated managed-repository worktree under `/data/repository`;
- validates local candidates before committing them to the managed Home Assistant repository;
- fetches and classifies managed-repository state as equal, local-ahead, remote-ahead, remote-only, or diverged;
- refuses push/apply operations on diverged history;
- treats fetched Git trees as untrusted input;
- rejects blocked paths, symlinks/special modes, oversized content, and malformed YAML/JSON/Python;
- stages accepted remote candidates under `/data/staging`, never directly in `/homeassistant`;
- blocks remote apply when live allowed configuration has drifted from the local Git baseline;
- creates a persistent local transaction snapshot and synchronous Supervisor partial backup before live mutation;
- pins staged writes with SHA-256 across the backup window;
- applies only policy-approved regular files and genuine deletions using atomic replacement;
- runs Supervisor `/core/check` before restart;
- verifies Home Assistant Core health after restart;
- rolls back prior files/Core state when apply or verification fails;
- recovers interrupted transactions before any new synchronization;
- re-fetches the managed repository before final Git adoption so remote movement causes rollback;
- retains a bounded set of SyncApp-created pre-apply backups without touching protected or unrelated backups.

There is **no direct `git pull` into `/homeassistant`**. Git checkout/reset/clean operations are confined to `/data/repository`.

## Configuration

- `homeassistant_repository_url`: GitHub repository that stores the Home Assistant configuration and is read/written by SyncApp. It must be separate from the SyncApp source repository.
- `repository_url`: deprecated compatibility alias for `homeassistant_repository_url`; do not use for new installations.
- `branch`: branch within the managed Home Assistant repository, normally `main`.
- `github_token`: token for the managed Home Assistant repository. Credentials are passed to Git through process environment configuration and are not embedded in the remote URL.
- `poll_interval_seconds`: synchronization polling interval; minimum 30 seconds.
- `dry_run`: defaults to `true`. No local push or remote live apply occurs while enabled.
- `remote_apply_enabled`: defaults to `false`. Remote live writes require this to be `true` and `dry_run` to be `false`.
- `verify_timeout_seconds`: Core-health timeout after restart; default 120 seconds.
- `backup_retention_count`: defaults to `10`. `0` disables cleanup. Only old unprotected backups positively identified by the `SyncApp pre-apply ` prefix are candidates.
- `git_user_name` / `git_user_email`: identity used for generated commits in the managed Home Assistant repository.

## Local → GitHub

Local Home Assistant changes are mirrored into `/data/repository`, filtered through the same secret/runtime policy, and statically checked for size and syntax. SyncApp also runs Supervisor `/core/check` against the live configuration before creating a Git commit.

If validation fails or `dry_run` is enabled, the rejected candidate is removed from the isolated Git index/worktree; `/homeassistant` remains untouched. SyncApp also refuses to create a new commit when the managed repository already tracks a blocked secret/runtime path.

A failed push leaves the isolated branch local-ahead so a later cycle can retry the push without rebuilding or mutating the live configuration.

## GitHub → Local safety model

### Detect / Fetch

SyncApp fetches only into `/data/repository`. A diverged history is blocked. Before a remote update can touch live files, allowed live configuration must match the current local Git baseline.

### Stage / static Validate

Remote tree entries are treated as untrusted. Blocked paths such as `secrets.yaml`, `.storage`, databases, logs, caches, private-key material, symlinks, unsupported Git modes, and excessive content are rejected before staging. YAML/JSON and Python custom-component syntax are checked under `/data/staging`.

Static validation is not treated as proof of Home Assistant semantic validity; Supervisor `/core/check` remains authoritative after recoverable application.

### Backup / Apply

Before mutation SyncApp writes a durable transaction journal under `/data/transaction`, snapshots every existing affected managed file, and requests a synchronous Supervisor partial Home Assistant backup. No live file is modified until that backup succeeds.

Every staged write has a SHA-256 digest recorded in the journal. After backup, SyncApp proves both that affected live targets still match their pre-backup snapshot and that staged sources still match their recorded hashes. A copied temporary file is hashed again before atomic replacement.

If local content changes during the backup window, the transaction is aborted without overwriting that edit.

### Verify / adoption

After recoverable application, SyncApp calls `/core/check`. A failed check restores prior files without restarting the still-running old Core process. A successful check is followed by Core restart and Core API health verification.

Only after health succeeds does SyncApp re-fetch the managed GitHub branch, prove the candidate commit is still the configured remote head, adopt that exact commit in `/data/repository`, update the managed-file manifest, and complete the transaction. If the branch moved, the live update is rolled back.

### Rollback / crash recovery

If post-restart health fails, prior files are restored and the old configuration is checked, restarted, and health-verified. When rollback health cannot be proven, the transaction journal/snapshot is preserved rather than discarded.

Interrupted transaction state is always handled before new Git activity. Pre-mutation states can be discarded without restarting Core; states that may have changed live files are rolled back and verified first.

A special post-verification crash window is handled conservatively. When the verified commit was already adopted in Git, SyncApp finalizes bookkeeping only if both Git HEAD and the live managed configuration still match that commit. Ambiguous drift blocks both automatic finalize and rollback and preserves recovery evidence.

## Backup retention

Retention runs only after a remote transaction has been verified, adopted, manifested, and completed. Cleanup failure is non-fatal. A backup is eligible only when its name begins with `SyncApp pre-apply `, Supervisor reports `protected: false`, the slug and timestamp are valid, and it is not the just-created transaction backup. All ambiguous, protected, manual, and unrelated backups are preserved.

## Supervisor canary

The image includes `/app/canary.py` to exercise Supervisor integration without changing Home Assistant configuration files.

```sh
python3 /app/canary.py
python3 /app/canary.py --backup
python3 /app/canary.py --backup --restart --timeout 120
```

The restart form explicitly restarts Core. A disposable/canary HAOS installation should pass these probes before `remote_apply_enabled` is used anywhere important, followed by a harmless reversible configuration-only remote-apply test.

## Test coverage

CI covers secret/runtime policy, Git relationship states and empty repositories, remote staging validation, malformed YAML/JSON/Python, Git symlink rejection, staged SHA-256 integrity, live drift, minimal apply plans, Supervisor request contracts, conservative backup retention, backup-window race injection, semantic-check failure, post-restart rollback, rollback-health failure, interrupted/ambiguous crash recovery, local pre-push validation, first push to an empty Git repository, static type checking, metadata validation, and Docker image build.

## Experimental status

Repository-level safety is heavily failure-injected, but local CI cannot prove real Supervisor backup semantics, bind-mounted `/homeassistant` filesystem behavior, `/core/check`, Core restart/health transitions, or backup inventory/deletion on Home Assistant OS hardware.

Keep `remote_apply_enabled: false` on important instances until the current stack passes a disposable HAOS/Supervisor canary.
