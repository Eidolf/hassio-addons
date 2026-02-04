#!/bin/bash
set -e

echo "[Add-on] Starting Google Find My Tools Add-on..."

# Start Xvfb
echo "[Add-on] Starting Xvfb..."
export DISPLAY=:1
Xvfb :1 -screen 0 1280x800x24 &
sleep 2

# Start Fluxbox
echo "[Add-on] Starting Fluxbox..."
fluxbox &

# Start x11vnc
echo "[Add-on] Starting x11vnc..."
x11vnc -display :1 -forever -shared -nopw -quiet &

# Start noVNC (websockify)
echo "[Add-on] Starting noVNC..."
# We forward internal port 5900 (VNC) to 8099 (Ingress)
/opt/novnc/utils/websockify/run --web /opt/novnc 8099 localhost:5900 &

echo "[Add-on] Starting Application..."

# Run the python app
# We use 'stdbuf' to unbuffer output so it shows in HA logs instantly
python -u main.py

# When main.py exits, we copy secrets if they exist
echo "[Add-on] customized main.py finished."

if [ -f "Auth/secrets.json" ]; then
    echo "[Add-on] Found secrets.json. Copying to /share/google_find_my_secrets.json..."
    cp Auth/secrets.json /share/google_find_my_secrets.json
    chmod 666 /share/google_find_my_secrets.json
    echo "[Add-on] Secrets copied successfully!"
else
    echo "[Add-on] No secrets.json found in Auth/."
fi

echo "[Add-on] Exiting..."
