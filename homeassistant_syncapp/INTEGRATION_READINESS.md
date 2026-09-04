# Cumulative integration readiness

This document records the review boundary for the cumulative HomeAssistant SyncApp safety stack. It is intentionally stricter than the status of any individual stacked pull request.

## Pinned integration candidate

At creation of this candidate:

- `main`: `e8e2f75596e94d3134ca24407268c202fd18a329`
- cumulative safety head before this document: `0313b7ad0b2e85c285a66a98b565b2b2d2f67af1`
- relationship: 630 commits ahead of `main`, 0 behind
- exact cumulative head CI: GitHub Actions run #990 passed Docker build, Python compilation, mypy, all 416 tests, and app metadata validation

The deep stacked PR chain is useful for incremental review, but it is not a substitute for validating the cumulative product as a whole. This integration branch exists to provide a single review/CI surface against `main`.

The integration CI also smoke-tests the startup bootstrap **inside the built Home Assistant base image**. It invokes the image's shipped `/usr/bin/python3 -E -s -B`, imports `/app/process_bootstrap.py`, proves the long-lived service environment allowlist, verifies hostile proxy/Git/Python/dynamic-loader inputs are omitted, and proves the Supervisor token is not placed in service argv. The final `execve` is intercepted only inside that smoke process so CI does not contact Supervisor or start the long-running service loop.

## Non-negotiable update workflow

The integrated implementation must preserve:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

The integration candidate must be rejected if any change introduces a blind Git pull/reset/checkout into `/homeassistant`, bypasses staged validation or the Supervisor backup gate, weakens rollback verification, or treats live Home Assistant configuration as a Git working tree.

## Secret and runtime exclusions

The cumulative candidate must continue to exclude secrets and runtime state from managed Git content and remote apply. In particular, `secrets.yaml`, `.storage`, databases, logs, caches, private keys/certificates, temporary/runtime files, Git control paths, traversal paths, and other policy-blocked content remain non-negotiable exclusions.

## Repository separation

The SyncApp source repository and the managed Home Assistant configuration repository remain separate trust domains. The managed repository is configured independently, persists under `/data/repository`, and the SyncApp source repository must be rejected as a managed target.

## What CI proves

The cumulative CI suite provides deterministic evidence for static/type correctness, unit/integration/failure-injection behavior, policy enforcement, transaction/recovery invariants, Git provenance and environment isolation, staging/live filesystem confinement, Supervisor contract handling, backup/archive validation, image buildability, and the built-image bootstrap/environment contract described above.

CI does **not** prove the behavior of a real Home Assistant OS/Supervisor installation, including mount/filesystem semantics, real Supervisor backup materialization/latency, `/core/check`, Core restart/health transitions, add-on container environment injection and shebang behavior, or power-loss/reboot recovery on the target platform.

## Merge gate

This cumulative integration PR is a review and validation surface, not authorization to merge. Do not merge it into `main` until disposable Home Assistant OS/Supervisor evidence has exercised the cumulative head and confirmed at minimum:

- initial-authority/bootstrap behavior for both allowed authority modes and ambiguous first-sync refusal;
- policy-blocked secret/runtime preservation;
- staged remote validation and destructive-deletion budgeting;
- verified Supervisor backup creation and continuity before/through live mutation;
- `/core/check` rejection and successful validation paths;
- Core restart, health verification, rollback, and rollback-health failure behavior;
- repository provenance and source/managed-repository separation;
- staging, live-tree, transaction, manifest, and recovery filesystem semantics on the actual add-on mounts;
- interrupted/crash/reboot recovery from representative transaction states;
- process/environment/bootstrap assumptions that depend on the Home Assistant base image and Supervisor runtime.

Failed target-runtime evidence must be preserved and fixed on a new incremental branch; it must never be bypassed by weakening the workflow or exclusions.
