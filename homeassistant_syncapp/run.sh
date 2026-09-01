#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HomeAssistant SyncApp"
exec python3 /app/main.py
