#!/usr/bin/with-contenv bashio
set -euo pipefail

export PATH="/usr/bin:/bin"
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONBREAKPOINT PYTHONPYCACHEPREFIX
export PYTHONNOUSERSITE="1"
unset LD_PRELOAD LD_LIBRARY_PATH LD_AUDIT LD_DEBUG LD_DEBUG_OUTPUT LD_PROFILE LD_PROFILE_OUTPUT

bashio::log.info "Starting HomeAssistant SyncApp"
exec /usr/bin/python3 -E -s -B /app/main.py
