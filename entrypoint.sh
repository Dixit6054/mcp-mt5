#!/bin/bash
set -e

# Ensure /root/.wine is owned by root (bind mounts can carry host UID permissions)
if [ -d "/root/.wine" ]; then
    chown -R root:root /root/.wine
fi

# 1. Start Xvfb in background
echo "Starting Xvfb on DISPLAY ${DISPLAY}..."
rm -f /tmp/.X99-lock
Xvfb ${DISPLAY} -screen 0 1024x768x16 &
XVFB_PID=$!
sleep 2

# 2. Start x11vnc in background to expose graphical UI
echo "Starting x11vnc on port 5900..."
x11vnc -display ${DISPLAY} -forever -shared -nopw -bg -rfbport 5900 &
VNC_PID=$!
sleep 2

# 3. Run config validator
echo "Validating configuration files..."
/usr/local/bin/config-validator.sh

MT5_INSTALL_DIR="/root/.wine/drive_c/Program Files/MetaTrader 5"

# 4. First-run auto-installer check
if [ ! -f "${MT5_INSTALL_DIR}/terminal64.exe" ]; then
    echo "MetaTrader 5 terminal64.exe not found. Initializing Wine prefix and installing MT5 natively..."
    
    # Configure Wine to emulate Windows 11
    winecfg -v=win11
    sleep 2
    
    # Download and install WebView2 Runtime (silent)
    echo "Downloading and installing WebView2..."
    curl -L "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/f2910a1e-e5a6-4f17-b52d-7faf525d17f8/MicrosoftEdgeWebview2Setup.exe" -o /tmp/webview2.exe
    wine /tmp/webview2.exe /silent /install || true
    sleep 5
    
    # Download and install MT5 (silent/auto)
    echo "Downloading and installing MetaTrader 5..."
    curl -L "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" -o /tmp/mt5setup.exe
    wine /tmp/mt5setup.exe /auto || true
    
    echo "Awaiting MT5 installation to complete..."
    while [ ! -f "${MT5_INSTALL_DIR}/terminal64.exe" ]; do
        sleep 2
    done
    echo "MetaTrader 5 installed successfully."
    
    # Clean up installers and wait for wineserver to flush
    rm -f /tmp/webview2.exe /tmp/mt5setup.exe
    sleep 5
    wineserver -w || true
fi

# 5. Mount files to the portable directories
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

# 6. Handle exit signals for graceful termination
cleanup() {
    echo "Stopping MetaTrader 5..."
    wineserver -k || true
    echo "Stopping x11vnc..."
    kill $VNC_PID || true
    echo "Stopping Xvfb..."
    kill $XVFB_PID || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# 7. Launch MT5 Terminal in portable mode
echo "Launching MT5 Terminal in portable mode..."
WINEDLLOVERRIDES="mscoree,mshtml=" wine "${MT5_INSTALL_DIR}/terminal64.exe" /portable /config:C:\\startup.ini &
MT5_PID=$!

wait $MT5_PID
