# Managed Git repository provenance

SyncApp treats the isolated Git clone under `/data/repository` as safety-critical persistent state. Its history, managed-path manifest, and transaction evidence all belong to one configured Home Assistant repository **and one configured branch**.

## Bound identity

For an existing managed clone, SyncApp requires all of the following before any fetch or push:

- the configured `homeassistant_repository_url` identifies the same repository as the clone's `origin` fetch URL;
- `origin` has exactly one effective fetch URL;
- every effective `origin` push URL identifies that same configured repository;
- the currently checked-out persistent branch exactly matches the configured `branch`.

The provenance check is repeated immediately before every network `fetch` and `push`, not only at process startup. This prevents a later change to `.git/config` from silently redirecting synchronization after the initial validation.

## Why push URLs are checked separately

Git permits `remote.origin.pushurl` to differ from the fetch URL and permits more than one push URL. Without an explicit check, a clone could fetch trusted Home Assistant configuration from the approved repository while local configuration commits are pushed to another destination.

SyncApp therefore rejects any effective push URL whose repository identity differs from `homeassistant_repository_url`. It never repairs or overwrites an unexpected push URL automatically because doing so would hide persistent-state tampering or operator error.

## Branch changes

Changing the configured `branch` on an existing `/data/repository` is also fail-closed. The managed-path manifest and transaction provenance describe the baseline associated with the existing branch; silently checking out another branch would reuse that state against a different Git history.

To move an installation to another repository or branch, treat it as an explicit migration/reinitialization operation. Preserve any needed backups and configuration first, then intentionally reset the SyncApp-managed `/data` state rather than relying on an option change to retarget it.

## Safety boundary

These checks do not change the remote-update workflow:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Roll back if necessary**

No Git checkout, reset, or pull is performed directly against `/homeassistant`. Secret/runtime exclusions remain unchanged and apply independently of repository provenance checks.
