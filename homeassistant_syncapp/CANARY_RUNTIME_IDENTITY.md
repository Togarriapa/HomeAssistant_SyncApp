# Canary runtime identity binding

Disposable Home Assistant OS/Supervisor evidence must be attributable to the exact image bytes that passed repository CI. The add-on image does not contain a trustworthy Git checkout, so a commit SHA observed inside the container is not sufficient evidence.

`/app/runtime_fingerprint.py` computes a deterministic SHA-256 fingerprint over `/run.sh` plus every regular file shipped under `/app`, rejecting symlinked or non-regular runtime inputs. CI executes that fingerprint inside the freshly built image.

For target-runtime acceptance, use `/app/canary_evidence.py` instead of invoking `/app/canary.py` directly. Supply the SHA-256 printed by the exact candidate's green Docker CI job:

```text
python3 /app/canary_evidence.py --expected-runtime-sha256 <64-hex-ci-fingerprint>
```

The wrapper verifies the runtime fingerprint **before constructing a Supervisor client or running any canary operation**. A mismatch therefore fails before backup creation, filesystem write probes, Core restart, or other optional canary actions.

The Docker CI job also exercises the same shipped wrapper in `--identity-only` mode against the fingerprint produced by that exact image. Identity-only mode requires an expected digest, cannot be combined with canary operation flags, and exits without constructing a Supervisor client. This proves the image used for CI can successfully enforce the same preflight that will be required on HAOS.

All existing canary options remain available for target-runtime evidence, for example:

```text
python3 /app/canary_evidence.py \
  --expected-runtime-sha256 <64-hex-ci-fingerprint> \
  --filesystem
```

and, only on a disposable HAOS/Supervisor installation after the non-mutating checks pass:

```text
python3 /app/canary_evidence.py \
  --expected-runtime-sha256 <64-hex-ci-fingerprint> \
  --filesystem \
  --backup \
  --restart \
  --timeout 120
```

The emitted JSON contains a `runtime_image` object together with the existing redacted HAOS/Core/Supervisor and canary evidence. Preserve the complete JSON result with the candidate commit and CI run number.

This binding is evidence only. It does not authorize synchronization, alter the managed Git repository, touch `/homeassistant` through Git, relax blocked-file policy, or replace the real target-runtime acceptance scenarios tracked in issue #4.

The synchronization lifecycle remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**.
