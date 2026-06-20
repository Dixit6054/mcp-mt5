#!/bin/bash
set -e

# 1. Start Xvfb in background
echo "Starting Xvfb on DISPLAY ${DISPLAY}..."
rm -f /tmp/.X99-lock
Xvfb ${DISPLAY} -screen 0 1024x768x16 &
XVFB_PID=$!
sleep 2

# 2. Run config validator
echo "Validating configuration files..."
/usr/local/bin/config-validator.sh

# 3. Mount files to the portable directories
MT5_INSTALL_DIR="/root/.wine/drive_c/Program Files/MetaTrader 5"
CONFIG_DIR="/etc/mt5/config"

echo "Copying config files and EA/presets..."
mkdir -p "${MT5_INSTALL_DIR}/MQL5/Experts"
mkdir -p "${MT5_INSTALL_DIR}/MQL5/Presets"

# Copy startup.ini to drive_c
if [ -f "${CONFIG_DIR}/startup.ini" ]; then
    cp "${CONFIG_DIR}/startup.ini" "/root/.wine/drive_c/startup.ini"
fi

# Copy EA binaries if present
if ls "${CONFIG_DIR}"/*.ex5 >/dev/null 2>&1; then
    cp "${CONFIG_DIR}"/*.ex5 "${MT5_INSTALL_DIR}/MQL5/Experts/"
fi

# Copy presets if present
if ls "${CONFIG_DIR}"/*.set >/dev/null 2>&1; then
    cp "${CONFIG_DIR}"/*.set "${MT5_INSTALL_DIR}/MQL5/Presets/"
fi

# 4. Handle exit signals for graceful termination
cleanup() {
    echo "Stopping MetaTrader 5..."
    wineserver -k || true
    echo "Stopping Xvfb..."
    kill $XVFB_PID || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# 5. Launch MT5 Terminal in portable mode
echo "Launching MT5 Terminal in portable mode..."
WINEDLLOVERRIDES="mscoree,mshtml=" wine "${MT5_INSTALL_DIR}/terminal64.exe" /portable /config:C:\\startup.ini &
MT5_PID=$!

wait $MT5_PID
