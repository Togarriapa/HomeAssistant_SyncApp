# Git UI and diff helper safety

SyncApp runs Git as a non-interactive control-plane tool. It never needs a user-selected pager, editor, sequence editor, or external diff program.

Every SyncApp Git subprocess therefore replaces inherited helper selections with fixed system commands:

- `GIT_PAGER=/bin/cat` and `PAGER=/bin/cat`
- `GIT_EDITOR=/bin/false` and `GIT_SEQUENCE_EDITOR=/bin/false`
- `EDITOR=/bin/false` and `VISUAL=/bin/false`
- `GIT_EXTERNAL_DIFF=/bin/false`
- inherited `GIT_DIFF_OPTS` is removed

This prevents ambient runtime state from turning a later Git command into execution of an attacker-selected pager, editor, or diff helper. The fixed false editor/diff commands also fail closed if future code accidentally requests an interactive editor or external diff path.

The live Home Assistant workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and secret/runtime exclusions are unchanged.