#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Add-on: ER-Adlernest
# Launch script
# ==============================================================================

bashio::log.info "Starting ER-Adlernest (Eagle Eye CCTV & Archive Manager)..."

DATA_DIR="/data"
mkdir -p "${DATA_DIR}"
mkdir -p "${DATA_DIR}/thumbnails"
mkdir -p "${DATA_DIR}/db"

# Export Supervisor Token if provided by Hassio
if bashio::config.has_value "log_level"; then
    export LOG_LEVEL=$(bashio::config 'log_level')
fi

bashio::log.info "Starting ER-Adlernest backend on port 8098..."
cd /app/backend
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8098
