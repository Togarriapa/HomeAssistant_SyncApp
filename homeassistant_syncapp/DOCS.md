# HomeAssistant SyncApp

## Current development milestone

Version `0.1.0` implements the first safe half of the synchronization engine and the initial remote staging boundary:

- read the Home Assistant configuration from `/homeassistant`;
- exclude secrets, runtime state, databases, logs, caches, keys, certificates, and generated files;
- mirror allowed files into an isolated Git worktree under `/data`;
- commit and push local changes when `dry_run` is disabled;
- fetch and classify remote Git state as equal, local-ahead, remote-ahead, remote-only, or diverged;
- refuse pushes when remote history is ahead or diverged;
- enumerate a remote commit as untrusted Git tree data before materializing it;
- reject blocked paths, symlinks/special Git modes, oversized files, and oversized trees;
- materialize accepted remote files only into `/data/staging`;
- syntax-check staged YAML/YML (including Home Assistant custom tags) and JSON;
- preserve the previous staging snapshot if a new candidate fails validation.

Remote-to-local **live application remains intentionally disabled**. The app does not perform a direct `git pull` into `/homeassistant`, and passing staging validation is not permission to modify the live configuration.

## Configuration

- `repository_url`: target GitHub configuration repository. This is separate from the repository containing SyncApp itself.
- `branch`: branch to synchronize, normally `main`.
- `github_token`: GitHub token used for authenticated Git operations. It is passed to Git through process environment configuration rather than being embedded in the remote URL.
- `poll_interval_seconds`: synchronization polling interval. Minimum 30 seconds.
- `dry_run`: defaults to `true`. When enabled, local changes are detected and logged but no commit is pushed.
- `git_user_name` / `git_user_email`: identity used for automatically generated commits.

## Safety model

The target remote-to-local workflow is:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

The current implementation reaches **Stage → static Validate** only. Static validation deliberately does not claim that Home Assistant will accept the configuration semantically.

The next remote-apply milestone must add a backup and reversible application transaction around the live configuration. The Supervisor `/core/check` endpoint validates the live mounted configuration rather than an arbitrary staging directory, so semantic validation must be performed only after a recoverable backup/snapshot and before any restart. A failed semantic check, failed restart, or failed health verification must restore the previously known working configuration.
