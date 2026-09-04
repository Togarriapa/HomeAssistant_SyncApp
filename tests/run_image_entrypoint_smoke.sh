#!/bin/sh
set -eu

IMAGE_NAME="${1:-homeassistant-syncapp:test}"
EVIDENCE_DIR="$(mktemp -d)"
SHIM_PATH="${EVIDENCE_DIR}/python3-shim"
EVIDENCE_PATH="${EVIDENCE_DIR}/entrypoint-evidence.txt"

cleanup() {
    rm -rf "${EVIDENCE_DIR}"
}
trap cleanup EXIT INT TERM

cat >"${SHIM_PATH}" <<'SHIM'
#!/bin/sh
set -eu
{
    printf 'argc=%s\n' "$#"
    index=0
    for argument in "$@"; do
        printf 'argv[%s]=%s\n' "${index}" "${argument}"
        index=$((index + 1))
    done
    printf '%s\n' '--- environment ---'
    /usr/bin/env | /usr/bin/sort
} > /evidence/entrypoint-evidence.txt
SHIM
chmod 0755 "${SHIM_PATH}"

docker run --rm \
    --volume "${SHIM_PATH}:/usr/bin/python3:ro" \
    --volume "${EVIDENCE_DIR}:/evidence" \
    --env 'SUPERVISOR_TOKEN=entrypoint-smoke-token' \
    --env 'TZ=Europe/Lisbon' \
    --env 'LANG=C.UTF-8' \
    --env 'PATH=/untrusted/bin:/usr/bin:/bin' \
    --env 'PYTHONPATH=/untrusted/python' \
    --env 'PYTHONHOME=/untrusted/home' \
    --env 'PYTHONSTARTUP=/untrusted/startup.py' \
    --env 'PYTHONINSPECT=1' \
    --env 'PYTHONBREAKPOINT=untrusted.breakpoint' \
    --env 'PYTHONPYCACHEPREFIX=/untrusted/pycache' \
    --env 'LD_LIBRARY_PATH=/untrusted/lib' \
    --env 'LD_AUDIT=/untrusted/audit.so' \
    --env 'LD_DEBUG=libs' \
    --env 'LD_DEBUG_OUTPUT=/untrusted/ld-debug' \
    --env 'LD_PROFILE=libc.so' \
    --env 'LD_PROFILE_OUTPUT=/untrusted/profile' \
    --env 'HTTPS_PROXY=http://untrusted.invalid:8080' \
    --env 'GIT_DIR=/untrusted/git' \
    "${IMAGE_NAME}"

test -s "${EVIDENCE_PATH}"
grep -Fx 'argc=4' "${EVIDENCE_PATH}"
grep -Fx 'argv[0]=-E' "${EVIDENCE_PATH}"
grep -Fx 'argv[1]=-s' "${EVIDENCE_PATH}"
grep -Fx 'argv[2]=-B' "${EVIDENCE_PATH}"
grep -Fx 'argv[3]=/app/process_bootstrap.py' "${EVIDENCE_PATH}"
for forbidden in \
    PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONBREAKPOINT \
    PYTHONPYCACHEPREFIX LD_PRELOAD LD_LIBRARY_PATH LD_AUDIT LD_DEBUG \
    LD_DEBUG_OUTPUT LD_PROFILE LD_PROFILE_OUTPUT
do
    if grep -q "^${forbidden}=" "${EVIDENCE_PATH}"; then
        echo "forbidden environment variable survived /run.sh: ${forbidden}" >&2
        exit 1
    fi
done
grep -Fx 'PATH=/usr/bin:/bin' "${EVIDENCE_PATH}"
grep -Fx 'PYTHONNOUSERSITE=1' "${EVIDENCE_PATH}"
grep -Fx 'SUPERVISOR_TOKEN=entrypoint-smoke-token' "${EVIDENCE_PATH}"
grep -Fx 'HTTPS_PROXY=http://untrusted.invalid:8080' "${EVIDENCE_PATH}"
grep -Fx 'GIT_DIR=/untrusted/git' "${EVIDENCE_PATH}"
if head -n 5 "${EVIDENCE_PATH}" | grep -q 'entrypoint-smoke-token'; then
    echo 'Supervisor token leaked into entrypoint argv' >&2
    exit 1
fi
