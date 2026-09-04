# Confined local-to-Git mirror

Local publication is an outbound operation: SyncApp copies policy-approved Home Assistant configuration into its isolated Git worktree, validates that candidate, asks Home Assistant to validate the live configuration semantically, and only then may commit and push. It must never use mutable path traversal to turn a local filesystem race into secret disclosure or an out-of-tree write.

## Live source boundary

`mirror_local_configuration()` opens the Home Assistant source root through `PinnedReadRoot`. Policy-approved files are enumerated relative to opened no-follow directory descriptors. Each source leaf is then opened with `O_NOFOLLOW` relative to its pinned parent and read only while its leaf, ancestor, and root identities remain stable.

Policy-blocked runtime directories and files remain excluded exactly as before. A policy-allowed symlink or other non-regular entry is rejected rather than followed or silently converted into Git content.

The allowed source path set is enumerated again after the copies. A concurrent add/remove that changes the publish set fails closed instead of producing an ambiguous local candidate.

## Isolated Git destination boundary

`MirrorFilesystem` opens the isolated repository root once with `O_DIRECTORY | O_NOFOLLOW`. Parent directories are traversed or created relative to opened descriptors and symlinked parents are refused.

Writes use an exclusive transaction-owned temporary leaf followed by descriptor-relative `os.replace()`. Existing non-regular destination leaves are rejected, so a pre-existing symlink cannot redirect a configuration write outside the isolated Git worktree. Managed deletions are likewise descriptor-relative and refuse non-regular leaves.

Root pathname identity is rechecked after mutations. Confinement failures are surfaced as `ManifestError` and local publication stops before Git commit or push.

## Remote-update invariants

This outbound hardening does not alter remote application. Remote updates remain:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

There is no blind `git pull` into `/homeassistant`, and secret/runtime exclusions remain non-negotiable, including `secrets.yaml`, `.storage`, databases, logs, private key/certificate material, PID/lock/temp files, and `.git` content.
