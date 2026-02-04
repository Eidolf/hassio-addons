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


echo "[Add-on] Starting Application in Interactive Terminal..."

# Remove potentially stale secrets
if [ -f "Auth/secrets.json" ]; then
    echo "[Add-on] Removing stale Auth/secrets.json..."
    rm Auth/secrets.json
fi

# Run the python app inside xterm so user can interact via VNC
# We chain commands: run app -> copy secrets -> keep window open for review
xterm -geometry 130x40 -title "Google Find My Tools - Interactive Shell" -e "python3 main.py; \
    if [ -f 'Auth/secrets.json' ]; then \
        echo '[Add-on] Found secrets.json. Copying to /share/google_find_my_secrets.json...'; \
        cp Auth/secrets.json /share/google_find_my_secrets.json; \
        chmod 666 /share/google_find_my_secrets.json; \
        echo '[Add-on] Secrets copied successfully!'; \
    else \
        echo '[Add-on] No secrets.json found in Auth/.'; \
    fi; \
    echo ''; \
    echo 'To test GCM registration fix, run: python3 test_gcm.py'; \
    echo 'If that works, you can edit Auth/firebase_messaging/fcmregister.py with the working headers.'; \
    echo 'Process finished. You can now close this window or the add-on.'; \
    read -p 'Press Enter to exit container...' var"

echo "[Add-on] Xterm session ended. Exiting..."

echo "[Add-on] Exiting..."
