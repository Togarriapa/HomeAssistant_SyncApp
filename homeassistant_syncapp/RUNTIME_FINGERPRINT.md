# Runtime image fingerprint evidence

Disposable Home Assistant OS/Supervisor acceptance evidence must be tied to the exact SyncApp runtime bytes that were tested. The add-on image does not contain a Git checkout, so a Git commit SHA cannot be trusted as an in-container fact by itself.

SyncApp therefore ships `/app/runtime_fingerprint.py`. It computes a deterministic SHA-256 fingerprint over the exact image-owned startup/runtime inputs:

- `/run.sh`;
- every regular file under `/app`, with stable path ordering and path/size framing.

The fingerprint reader opens files with no-follow semantics and rejects symlinked or non-regular runtime inputs. The digest is evidence only; it is never used to authorize synchronization, bypass validation, or make an apply decision.

CI runs the script inside the freshly built image and records its JSON result in the exact commit's Docker job. On the disposable HAOS/Supervisor target, run:

```text
python3 /app/runtime_fingerprint.py
```

Record that JSON next to the normal canary output and require the `schema`, `algorithm`, `sha256`, and `files` values to match the green CI run for the exact candidate being accepted. A mismatch means the deployed image bytes are not the same evidence set and the acceptance run must not be credited to that candidate.

This fingerprint supplements—not replaces—the exact GitHub candidate SHA, HAOS/Core/Supervisor version evidence, real backup verification, `/core/check`, restart/health verification, rollback testing, interrupted recovery, first-sync authority checks, provenance checks, and blocked-file preservation required by issue #4.

The synchronization lifecycle remains **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. Fingerprinting is read-only and does not touch `/homeassistant`, the managed Git repository, the transaction journal, or secret/runtime-file policy.
