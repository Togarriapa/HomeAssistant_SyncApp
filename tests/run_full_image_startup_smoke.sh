#!/bin/sh
set -eu

IMAGE_NAME="${1:-homeassistant-syncapp:test}"
EVIDENCE_DIR="$(mktemp -d)"
RECORDER_PATH="${EVIDENCE_DIR}/main.py"
EVIDENCE_PATH="${EVIDENCE_DIR}/full-startup-evidence.json"

cleanup() {
    rm -rf "${EVIDENCE_DIR}"
}
trap cleanup EXIT INT TERM

cat >"${RECORDER_PATH}" <<'PY'
import json
import os
import sys
from pathlib import Path

Path("/evidence/full-startup-evidence.json").write_text(
    json.dumps(
        {
            "argv": sys.argv,
            "environment": dict(os.environ),
        },
        sort_keys=True,
    ),
    encoding="utf-8",
)
PY

# Exercise the complete real startup path:
# Docker CMD -> /run.sh -> real process_bootstrap.py -> real /usr/bin/python3.
# Only /app/main.py is replaced with a recorder so the service loop never
# starts and no Supervisor/Git/live-filesystem operation can occur.
docker run --rm \
    --volume "${RECORDER_PATH}:/app/main.py:ro" \
    --volume "${EVIDENCE_DIR}:/evidence" \
    --env 'SUPERVISOR_TOKEN=full-startup-smoke-token' \
    --env 'TZ=Europe/Lisbon' \
    --env 'LANG=C.UTF-8' \
    --env 'LC_ALL=C.UTF-8' \
    --env 'PATH=/untrusted/bin:/usr/bin:/bin' \
    --env 'HOME=/untrusted/home' \
    --env 'HTTPS_PROXY=http://untrusted.invalid:8080' \
    --env 'HTTP_PROXY=http://untrusted.invalid:8080' \
    --env 'NO_PROXY=untrusted.invalid' \
    --env 'GIT_DIR=/untrusted/git' \
    --env 'GIT_CONFIG_GLOBAL=/untrusted/gitconfig' \
    --env 'PYTHONPATH=/untrusted/python' \
    --env 'PYTHONHOME=/untrusted/python-home' \
    --env 'PYTHONSTARTUP=/untrusted/startup.py' \
    --env 'LD_LIBRARY_PATH=/untrusted/lib' \
    --env 'LD_AUDIT=/untrusted/audit.so' \
    --env 'BASH_ENV=/untrusted/bash-env' \
    "${IMAGE_NAME}"

test -s "${EVIDENCE_PATH}"

python3 - "${EVIDENCE_PATH}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
evidence = json.loads(path.read_text(encoding="utf-8"))
expected_environment = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/bin:/bin",
    "PYTHONNOUSERSITE": "1",
    "SUPERVISOR_TOKEN": "full-startup-smoke-token",
    "TZ": "Europe/Lisbon",
}

assert evidence["argv"] == ["/app/main.py"], evidence["argv"]
assert evidence["environment"] == expected_environment, evidence["environment"]
assert "full-startup-smoke-token" not in " ".join(evidence["argv"])
PY
