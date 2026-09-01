# HomeAssistant SyncApp

## Current development milestone

Version `0.2.0` implements the complete safety pipeline for an **experimental, explicitly enabled** remote apply:

- read the Home Assistant configuration from `/homeassistant`;
- exclude secrets, runtime state, databases, logs, caches, keys, certificates, and generated files;
- mirror allowed files into an isolated Git worktree under `/data`;
- commit and push local changes when `dry_run` is disabled;
- fetch and classify remote Git state as equal, local-ahead, remote-ahead, remote-only, or diverged;
- refuse pushes and applies when Git history is diverged;
- enumerate a remote commit as untrusted Git tree data before materializing it;
- reject blocked paths, symlinks/special Git modes, oversized files, and oversized trees;
- materialize accepted remote files only into `/data/staging`;
- syntax-check staged YAML/YML (including Home Assistant custom tags), JSON, and Python custom-component files;
- preserve the previous staging snapshot if a new candidate fails validation;
- refuse remote application if allowed live configuration has drifted from the local Git HEAD;
- create both a local rollback snapshot/journal and a synchronous Supervisor partial backup before mutation;
- mutate only files that genuinely differ, plus genuine deletions;
- abort without overwriting a local edit if an affected live file changes while the Supervisor backup is running;
- copy or delete only policy-approved regular files using atomic replacement for writes;
- run the Supervisor Home Assistant configuration check after the recoverable file update and before restart;
- restart Home Assistant only after semantic validation succeeds;
- verify the Core API becomes healthy after restart through the Supervisor proxy;
- restore the prior files and, when required, restart/verify the prior configuration after a failed apply;
- recover interrupted transactions before performing any new Git synchronization;
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

The fetched remote tree is treated as untrusted input. Blocked paths such as `secrets.yaml`, `.storage`, databases, logs, caches, private-key material, symlinks, unsupported Git modes, and excessive content are rejected before staging. YAML and JSON syntax plus Python custom-component syntax are checked in `/data/staging` without modifying live Home Assistant files.

Static validation is not treated as proof that Home Assistant accepts the configuration semantically. The authoritative semantic check remains Supervisor `/core/check` against the recoverably updated live mount.

### Backup / Apply

Before live mutation, SyncApp records a persistent transaction journal under `/data/transaction`, snapshots every existing affected managed file, and then requests a synchronous Supervisor partial backup of Home Assistant. The backup request is allowed up to 15 minutes because no live file mutation occurs until it succeeds.

Only files that differ from the staged remote candidate are included in the write set; unchanged configuration files are not rewritten. After the backup completes, SyncApp proves every affected live target still matches the snapshot taken before the backup. If a local edit appeared during that window, SyncApp discards its transaction metadata and leaves that edit untouched.

Only paths allowed by the same policy used for local-to-GitHub synchronization can be written or deleted. A symlinked live configuration root, symlink targets, and symlinked parent directories are refused. Writes use a temporary sibling file followed by atomic replacement.

### Verify

After file application, SyncApp calls the Supervisor Core configuration check. If that fails, the prior files are restored without restarting the still-running old Core process.

If the check succeeds, SyncApp requests a Core restart. The Supervisor restart API waits for its restart operation; SyncApp then verifies Home Assistant itself is reachable through the Supervisor `/core/api/` proxy. Only after that succeeds does it re-fetch the configured Git branch, verify the remote commit did not move, adopt exactly the verified commit in the isolated Git worktree, update the managed-file manifest, and remove the transaction snapshot.

If the remote branch moved while backup/restart/verification was in progress, final Git adoption fails and the live configuration is rolled back rather than silently accepting a different commit.

### Rollback / crash recovery

If health verification fails after restart, the prior files are restored, checked, restarted, and health-verified. If rollback health itself cannot be proven, the transaction journal and snapshot are retained with a failure state rather than being discarded.

On every synchronization cycle, unresolved transaction state is handled before any new Git activity. States that are known to precede live mutation (`preparing`, `prepared`, or `backed_up`) are discarded without restarting Core. States that may have modified live files are rolled back and the prior Core configuration is validated/restarted/health-checked before synchronization can continue.

An empty transaction directory left in the tiny interval before the first journal write can be cleaned automatically. A non-empty transaction directory without a journal is treated as ambiguous corruption and blocks new work rather than guessing.

## Supervisor canary

The app image includes `/app/canary.py` for exercising the real Supervisor integration **without changing any Home Assistant configuration file**.

The default command is non-mutating with respect to configuration and performs Core info, Core API health, and `/core/check` calls:

```sh
python3 /app/canary.py
```

To additionally prove synchronous partial-backup creation:

```sh
python3 /app/canary.py --backup
```

The restart probe is intentionally separate and explicit because it restarts Home Assistant Core:

```sh
python3 /app/canary.py --backup --restart --timeout 120
```

A disposable/canary Home Assistant OS installation should pass all three levels before `remote_apply_enabled` is enabled anywhere important. The canary does not modify `/homeassistant`; the full remote-apply path should then be tested with a harmless, reversible configuration-only commit on that disposable instance.

## Test coverage

Repository CI now covers:

- policy and secret/runtime exclusion;
- Git relationship states including divergence and empty repositories;
- untrusted staging, malformed YAML/JSON/Python, Home Assistant custom tags, and Git symlink rejection;
- live-vs-HEAD drift detection;
- minimal apply-plan deletion/write behavior;
- Supervisor endpoint request/response contracts;
- Supervisor canary escalation behavior;
- backup failure before mutation;
- local edits occurring during the backup window;
- semantic-check failure before restart;
- post-restart health failure with verified rollback;
- rollback-health failure with recovery journal preservation;
- interrupted transaction recovery and preparation-state recovery;
- symlinked live paths/root rejection;
- an end-to-end local Git remote update with successful baseline adoption;
- a remote branch move during finalization causing rollback;
- a real Docker image build using the version declared in app metadata.

## Experimental status

The repository-level safety model is implemented and heavily failure-injected, but automated local tests cannot prove real Supervisor backup duration/semantics, bind-mounted `/homeassistant` filesystem behavior, `/core/check`, or Core restart/health transitions on Home Assistant OS hardware.

Keep `remote_apply_enabled: false` on any important instance until version `0.2.0` has passed the next milestone on a disposable/canary Home Assistant OS installation. That real-runtime canary is now the primary blocker to considering automatic remote apply production-ready.
