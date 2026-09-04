#!/usr/bin/with-contenv bashio
set -euo pipefail

export PATH="/usr/bin:/bin"

bashio::log.info "Starting HomeAssistant SyncApp"
exec /usr/bin/python3 /app/main.py
