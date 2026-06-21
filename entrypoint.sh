#!/bin/bash
set -e

# Ensure /root/.wine is owned by root (bind mounts can carry host UID permissions)
if [ -d "/root/.wine" ]; then
    chown -R root:root /root/.wine
fi

# 1. Start Xvfb in background (defaulting to standard widescreen 1920x1080)
SCREEN_RESOLUTION=${SCREEN_RESOLUTION:-1920x1080x16}
echo "Starting Xvfb on DISPLAY ${DISPLAY} with resolution ${SCREEN_RESOLUTION}..."
rm -f /tmp/.X99-lock
Xvfb ${DISPLAY} -screen 0 ${SCREEN_RESOLUTION} &
XVFB_PID=$!
sleep 2

# 2. Start x11vnc in background to expose graphical UI
echo "Starting x11vnc on port 5900..."
x11vnc -display ${DISPLAY} -forever -shared -nopw -bg -rfbport 5900 &
VNC_PID=$!
sleep 2

# 2b. Create custom Openbox window manager configuration to maximize main window and center popups
echo "Creating custom Openbox configuration..."
mkdir -p /root/.config/openbox
cat << 'EOF' > /root/.config/openbox/rc.xml
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc" xmlns:xi="http://www.w3.org/2001/XInclude">
  <applications>
    <!-- Maximize the main MetaTrader window (type="normal") -->
    <application type="normal">
      <maximized>yes</maximized>
    </application>
    <!-- Center dialogs/popups (type="dialog") instead of putting them at random coordinates -->
    <application type="dialog">
      <maximized>no</maximized>
      <position force="yes">
        <x>center</x>
        <y>center</y>
      </position>
    </application>
  </applications>
</openbox_config>
EOF

echo "Starting Openbox window manager..."
openbox &
OPENBOX_PID=$!
sleep 1

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
    echo "Stopping Openbox..."
    kill $OPENBOX_PID || true
    echo "Stopping x11vnc..."
    kill $VNC_PID || true
    echo "Stopping Xvfb..."
    kill $XVFB_PID || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# 6b. Set DPI/scaling inside Wine registry if WINE_DPI is set
WINE_DPI=${WINE_DPI:-120}
if [ "$WINE_DPI" -gt 0 ]; then
    DPI_HEX=$(printf '0x%02x' "$WINE_DPI")
    echo "Setting Wine DPI to ${WINE_DPI} (${DPI_HEX})..."
    wine reg add "HKEY_CURRENT_USER\Control Panel\Desktop" /v LogPixels /t REG_DWORD /d "$DPI_HEX" /f || true
    wine reg add "HKEY_CURRENT_USER\Software\Wine\Fonts" /v LogPixels /t REG_DWORD /d "$DPI_HEX" /f || true
fi

# 7. Launch MT5 Terminal in portable mode
echo "Launching MT5 Terminal in portable mode..."
WINEDLLOVERRIDES="mscoree,mshtml=" wine "${MT5_INSTALL_DIR}/terminal64.exe" /portable /config:C:\\startup.ini &
MT5_PID=$!

wait $MT5_PID
