#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Add-on: ER-Adlernest
# Launch script
# ==============================================================================

bashio::log.info "Starting ER-Adlernest (Eagle Eye CCTV & Archive Manager)..."

DATA_DIR="/data"
mkdir -p "${DATA_DIR}/thumbnails" "${DATA_DIR}/db" "${DATA_DIR}/mounts" "${DATA_DIR}/credentials"

# Export log level for the backend (validated there)
if bashio::config.has_value "log_level"; then
    export LOG_LEVEL=$(bashio::config 'log_level')
else
    export LOG_LEVEL="info"
fi

bashio::log.info "Starting ER-Adlernest backend on port 8098 (log_level=${LOG_LEVEL})..."
cd /app/backend
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8098 --log-level "${LOG_LEVEL}"
