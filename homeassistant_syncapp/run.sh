#!/usr/bin/with-contenv bashio
set -euo pipefail

export PATH="/usr/bin:/bin"
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONBREAKPOINT PYTHONPYCACHEPREFIX
export PYTHONNOUSERSITE="1"

bashio::log.info "Starting HomeAssistant SyncApp"
exec /usr/bin/python3 -E -s /app/main.py
