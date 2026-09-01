# HomeAssistant SyncApp

## Current development milestone

Version `0.1.0` implements the first safe half of the synchronization engine:

- read the Home Assistant configuration from `/homeassistant`;
- exclude secrets, runtime state, databases, logs, caches, keys, certificates, and generated files;
- mirror allowed files into an isolated Git worktree under `/data`;
- commit and push local changes when `dry_run` is disabled;
- fetch and detect a remote commit that is newer or divergent;
- refuse to push local changes while remote changes are pending.

Remote-to-local application is intentionally disabled in this milestone. The app must not perform a direct `git pull` into `/homeassistant`.

## Configuration

- `repository_url`: target GitHub configuration repository. This is separate from the repository containing SyncApp itself.
- `branch`: branch to synchronize, normally `main`.
- `github_token`: GitHub token used for authenticated Git operations. It is passed to Git through process environment configuration rather than being embedded in the remote URL.
- `poll_interval_seconds`: synchronization polling interval. Minimum 30 seconds.
- `dry_run`: defaults to `true`. When enabled, changes are detected and logged but no commit is pushed.
- `git_user_name` / `git_user_email`: identity used for automatically generated commits.

## Safety model

The target remote-to-local workflow is:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

The Supervisor API provides `/core/check`, backup endpoints, restart control, and runtime information. A future milestone will connect these primitives to the staged remote update path. Full Home Assistant semantic validation must occur before a restart, and any failed apply must restore the previously known working files.
