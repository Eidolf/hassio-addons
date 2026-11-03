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

STORAGE_TYPE=$(bashio::config 'storage_type')
SAMBA_ENABLED=$(bashio::config 'samba_enabled')

if bashio::var.true "${SAMBA_ENABLED}" || [ "${STORAGE_TYPE}" = "cifs" ]; then
    SERVER=$(bashio::config 'samba_server')
    SHARE=$(bashio::config 'samba_share')
    USERNAME=$(bashio::config 'samba_username')
    PASSWORD=$(bashio::config 'samba_password')
    MOUNT_TARGET="/mnt/nas_recordings"

    mkdir -p "${MOUNT_TARGET}"
    bashio::log.info "Mounting Samba/CIFS share: //${SERVER}/${SHARE} -> ${MOUNT_TARGET}"
    
    MOUNT_OPTS="ro,iocharset=utf8"
    if [ -n "${USERNAME}" ]; then
        MOUNT_OPTS="${MOUNT_OPTS},username=${USERNAME},password=${PASSWORD}"
    else
        MOUNT_OPTS="${MOUNT_OPTS},guest"
    fi

    if mount -t cifs "//${SERVER}/${SHARE}" "${MOUNT_TARGET}" -o "${MOUNT_OPTS}"; then
        bashio::log.info "Samba/CIFS share mounted successfully."
    else
        bashio::log.warning "Failed to mount CIFS share. Falling back to local/cached media."
    fi
fi

bashio::log.info "Starting ER-Adlernest backend on port 8098..."
cd /app/backend
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8098

