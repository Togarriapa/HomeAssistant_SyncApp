# Ignore-independent Git staging

SyncApp stages only the isolated managed repository under `/data`; it never stages files directly from `/homeassistant`. Managed source selection, protected secret/runtime exclusions, mirror confinement, and exact staged-tree verification are separate safety boundaries that run around this Git index operation.

Git ignore state is nevertheless a repository-local control surface. In particular, `$GIT_DIR/info/exclude` can hide a path from ordinary `git add`, and a stale or malicious `.gitignore` in the isolated worktree could do the same. Allowing those files to decide which already-approved managed paths reach the index makes Git metadata part of the content-selection policy.

`GitRepository.add_all()` therefore uses `git add -A -f`. The force flag means ignore rules cannot silently suppress a file that SyncApp has already selected and mirrored into the isolated repository. Deletions are still staged through `-A`.

This does **not** weaken the source exclusions. Files such as `secrets.yaml`, `.storage`, databases, logs, keys, certificates, and other protected runtime state are rejected before the isolated mirror is built; forcing Git to stage the isolated mirror cannot make those source files appear there. If unexpected state exists in the repository worktree, the existing exact staged-tree verification remains fail-closed rather than treating Git ignore rules as a security filter.

Regression coverage proves both `$GIT_DIR/info/exclude` and a worktree `.gitignore` can mark managed files ignored for ordinary Git while SyncApp still stages those approved files.

This milestone does not solve `$GIT_DIR/info/attributes`; attribute-driven filters remain a separate boundary requiring a filter-safe/index-construction design.

The remote-update workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No blind `git pull` is introduced and `/homeassistant` remains outside Git.
