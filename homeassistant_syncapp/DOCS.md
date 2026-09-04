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
- bind every staged write to a SHA-256 digest in the transaction journal and re-verify it after backup and before atomic replacement;
- mutate only files that genuinely differ, plus genuine deletions;
- abort without overwriting a local edit if an affected live file changes while the Supervisor backup is running;
- copy or delete only policy-approved regular files using atomic replacement for writes;
- run the Supervisor Home Assistant configuration check after the recoverable file update and before restart;
- restart Home Assistant only after semantic validation succeeds;
- verify the Core API becomes healthy after restart through the Supervisor proxy;
- restore the prior files and, when required, restart/verify the prior configuration after a failed apply;
- recover interrupted transactions before performing any new Git synchronization;
- fail closed when post-verification crash recovery cannot prove both the adopted Git baseline and matching live managed files;
- re-fetch GitHub before adopting a successfully verified remote commit as the local baseline;
- bind persistent Git state to the configured managed repository and branch, including separate Git push URLs;
- retain a bounded set of SyncApp-created pre-apply backups without touching protected or unrelated backups.

There is still **no direct `git pull` into `/homeassistant`**. Git checkout/reset operations only affect the isolated repository under `/data/repository`.

## Configuration

- `homeassistant_repository_url`: target GitHub repository containing the managed Home Assistant configuration. This is separate from the repository containing SyncApp itself. Deprecated `repository_url` is accepted only as an upgrade compatibility alias.
- `branch`: branch to synchronize, normally `main`. On an existing managed clone, changing the configured branch fails closed because the manifest and transaction state belong to the previous Git history.
- `github_token`: GitHub token used for authenticated Git operations against the managed Home Assistant repository. It is passed to Git through process environment configuration rather than being embedded in the remote URL.
- `poll_interval_seconds`: synchronization polling interval. Minimum 30 seconds.
- `dry_run`: defaults to `true`. No local push or remote live apply is performed while enabled.
- `remote_apply_enabled`: defaults to `false`. Remote live writes require this to be `true` **and** `dry_run` to be `false`.
- `initial_local_publish_enabled`: defaults to `false`. Explicitly authorizes the guarded local-authoritative first-sync case described in `BOOTSTRAP.md`.
- `initial_remote_apply_enabled`: defaults to `false`. Explicitly authorizes the guarded remote-authoritative first-sync case described in `BOOTSTRAP.md`; mutually exclusive with local-authoritative bootstrap.
- `verify_timeout_seconds`: maximum time to wait for Home Assistant Core to become healthy after a restart; default 120 seconds.
- `backup_retention_count`: defaults to `10`. After a successful remote transaction, SyncApp may delete older **unprotected backups whose names begin with `SyncApp pre-apply `**. `0` disables cleanup. Protected backups, unrelated/manual backups, backups with incomplete metadata, and the backup created for the just-completed transaction are never selected.
- `git_user_name` / `git_user_email`: identity used for automatically generated commits.

### Managed repository provenance

The clone under `/data/repository` is persistent safety state. SyncApp verifies that its effective `origin` fetch URL identifies exactly the configured managed repository and that every effective Git push URL resolves to that same target. The check is repeated immediately before each fetch and push so later `.git/config` changes cannot silently redirect synchronization.

The persistent checked-out branch must also equal the configured `branch`. Repository or branch changes are therefore explicit migrations rather than implicit option changes. See `REPOSITORY_PROVENANCE.md` for the complete contract and migration rationale.

## Safety model

The remote-to-local workflow is:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

### Detect / Fetch

The app fetches into an isolated Git worktree. Before each fetch it revalidates the managed remote provenance, including effective fetch and push destinations. A diverged history is blocked. Before an ordinary remote update can touch live files, the allowed live Home Assistant configuration must still match the local Git HEAD. This deliberately conservative rule avoids silently overwriting local edits that have not yet been committed and pushed.

### Stage / Validate

The fetched remote tree is treated as untrusted input. Blocked paths such as `secrets.yaml`, `.storage`, databases, logs, caches, private-key material, symlinks, unsupported Git modes, and excessive content are rejected before staging. YAML and JSON syntax plus Python custom-component syntax are checked in `/data/staging` without modifying live Home Assistant files.

Static validation is not treated as proof that Home Assistant accepts the configuration semantically. The authoritative semantic check remains Supervisor `/core/check` against the recoverably updated live mount.

### Backup / Apply

Before live mutation, SyncApp records a persistent transaction journal under `/data/transaction`, snapshots every existing affected managed file, and then requests a synchronous Supervisor partial backup of Home Assistant. The backup request is allowed up to 15 minutes because no live file mutation occurs until it succeeds.

The transaction journal records a SHA-256 digest for every staged file in the write set. After the Supervisor backup completes, SyncApp proves both that every affected live target still matches the pre-backup snapshot and that every staged source still matches its recorded digest. The copied temporary file is hashed again immediately before atomic replacement. This closes the backup-window TOCTOU path for both live and staged content.

Only files that differ from the staged remote candidate are included in the write set; unchanged configuration files are not rewritten. If a local edit appeared during the backup window, SyncApp discards its transaction metadata and leaves that edit untouched.

Only paths allowed by the same policy used for local-to-GitHub synchronization can be written or deleted. A symlinked live configuration root, symlink targets, and symlinked parent directories are refused. Writes use a temporary sibling file followed by atomic replacement.

### Verify

After file application, SyncApp calls the Supervisor Core configuration check. If that fails, the prior files are restored without restarting the still-running old Core process.

If the check succeeds, SyncApp requests a Core restart. The Supervisor restart API waits for its restart operation; SyncApp then verifies Home Assistant itself is reachable through the Supervisor `/core/api/` proxy. Only after that succeeds does it re-fetch the configured Git branch, verify the remote commit did not move, adopt exactly the verified commit in the isolated Git worktree, update the managed-file manifest, and remove the transaction snapshot.

If the remote branch moved while backup/restart/verification was in progress, final Git adoption fails and the live configuration is rolled back rather than silently accepting a different commit.

### Rollback / crash recovery

If health verification fails after restart, the prior files are restored, checked, restarted, and health-verified. If rollback health itself cannot be proven, the transaction journal and snapshot are retained with a failure state rather than being discarded.

On every synchronization cycle, unresolved transaction state is handled before any new Git activity. States that are known to precede live mutation (`preparing`, `prepared`, or `backed_up`) are discarded without restarting Core. States that may have modified live files are rolled back and the prior Core configuration is validated/restarted/health-checked before synchronization can continue.

A special crash window exists after a remote commit has already passed Core health verification and been adopted as the isolated Git baseline but before manifest/journal cleanup finishes. In that state SyncApp finalizes bookkeeping only if Git HEAD equals the verified commit **and** the live managed files still match that adopted baseline. If live drift is detected, the journal is marked `verified_drift` and both automatic finalization and rollback are blocked. If the Git baseline cannot be proven, recovery also stops without mutating live files. This avoids guessing in a state where either direction could destroy newer data.

An empty transaction directory left in the tiny interval before the first journal write can be cleaned automatically. A non-empty transaction directory without a journal is treated as ambiguous corruption and blocks new work rather than guessing.

### Backup retention

Successful remote applies create durable Supervisor partial backups as the last-resort recovery layer. To avoid unbounded storage growth, SyncApp can perform conservative post-success cleanup using `backup_retention_count`.

Retention runs only **after** the transaction has been verified, adopted in Git, manifested, and completed. Cleanup failure is logged but does not convert a successful apply into a rollback. Deletion candidates must positively satisfy all of these conditions:

- backup name begins with `SyncApp pre-apply `;
- Supervisor reports `protected: false`;
- slug is syntactically safe;
- creation date is present and parseable;
- the slug is not the backup created for the just-completed transaction.

Protected backups, manual/unrelated backups, ambiguous metadata, and the current transaction backup fail closed and are preserved.

## Home Assistant OS canary

The app image includes `/app/canary.py` for staged validation on a **disposable** Home Assistant OS installation. The canonical procedure and evidence fields are maintained in `CANARY.md`; use that file rather than treating the abbreviated commands below as the complete acceptance matrix.

The default command is configuration-non-mutating and checks the redacted runtime identity, Core API health, and `/core/check`:

```sh
python3 /app/canary.py
```

A read-only live-filesystem level proves descriptor-relative/no-follow access and hashes the complete policy-approved live tree before and after the run:

```sh
python3 /app/canary.py --filesystem
```

Only on the disposable canary, the explicit write probe creates, replaces, verifies, and removes **blocked random `*.tmp` files only**. It never intentionally edits a policy-approved Home Assistant configuration file:

```sh
python3 /app/canary.py --filesystem --filesystem-write-probe
```

The backup level creates a synchronous partial Home Assistant backup, verifies inventory and detail identity, proves Home Assistant content is present, and confirms the database-exclusion request:

```sh
python3 /app/canary.py --filesystem --backup
```

Core restart is gated behind that fresh verified backup:

```sh
python3 /app/canary.py --filesystem --backup --restart --timeout 120
```

For filesystem-backed levels, success also requires the policy-approved live path set and file contents to be unchanged after the probe. Secret/runtime exclusions remain unchanged, so logs, databases, `.storage`, `secrets.yaml`, keys/certificates, caches, and the canary's blocked temp files are outside that managed-configuration comparison.

These probes reduce ambiguity but do not replace the full issue #4 transaction exercise. Only after they pass should the disposable instance test a harmless remote commit through **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**. Keep remote apply disabled on important instances until the full real-runtime matrix passes.

## Test coverage

Repository CI now covers:

- policy and secret/runtime exclusion;
- Git relationship states including divergence and empty repositories;
- repository retargeting, separate/multiple push URL tampering, post-startup fetch/push redirection, and implicit branch-retarget refusal;
- untrusted staging, malformed YAML/JSON/Python, Home Assistant custom tags, and Git symlink rejection;
- staged-content SHA-256 pinning and mutation during the Supervisor backup window;
- live-vs-HEAD drift detection;
- minimal apply-plan deletion/write behavior;
- Supervisor endpoint request/response contracts, including backup inventory/detail lookup and scoped deletion;
- conservative backup-retention selection and protected/unrelated-backup preservation;
- staged Supervisor/filesystem canary escalation, backup-content evidence, restart gating, and live-configuration invariance;
- backup failure before mutation;
- local edits occurring during the backup window;
- semantic-check failure before restart;
- post-restart health failure with verified rollback;
- rollback-health failure with recovery journal preservation;
- interrupted transaction recovery, verified/adopted recovery ambiguity, and preparation-state recovery;
- symlinked live paths/root rejection;
- an end-to-end local Git remote update with successful baseline adoption;
- a remote branch move during finalization causing rollback;
- static type checking of the complete app source;
- a real Docker image build using the version declared in app metadata.

## Experimental status

The repository-level safety model is implemented and heavily failure-injected, but automated local tests cannot prove real Supervisor backup duration/semantics, bind-mounted `/homeassistant` filesystem behavior, `/core/check`, Core restart/health transitions, or backup inventory/detail behavior on Home Assistant OS hardware.

Keep `remote_apply_enabled: false` on any important instance until version `0.2.0` has passed the full disposable Home Assistant OS acceptance matrix in issue #4. Real-runtime validation is now the primary blocker to considering automatic remote apply production-ready.
