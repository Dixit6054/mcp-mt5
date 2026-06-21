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

# 5b. Force Auto Trading and WebRequest Configuration
echo "Configuring MT5 global settings and startup settings..."

# Enforce Experts settings in startup.ini (ASCII/UTF-8)
STARTUP_INI="/root/.wine/drive_c/startup.ini"
if [ ! -f "$STARTUP_INI" ]; then
    echo "Creating minimal startup.ini..."
    cat << 'EOF' > "$STARTUP_INI"
[Common]
[Experts]
Enabled=1
AllowDllImport=1
EOF
else
    echo "Enforcing Enabled=1 and AllowDllImport=1 in startup.ini..."
    awk '
    BEGIN {
        in_experts = 0
        found_experts = 0
        has_enabled = 0
        has_dll = 0
    }
    /^\[Experts\]/ {
        in_experts = 1
        found_experts = 1
        print
        next
    }
    /^\[/ && !/^\[Experts\]/ {
        if (in_experts) {
            if (!has_enabled) print "Enabled=1"
            if (!has_dll) print "AllowDllImport=1"
            in_experts = 0
        }
        print
        next
    }
    {
        if (in_experts) {
            clean_key = tolower($1)
            gsub(/[ \t\r\n]/, "", clean_key)
            if (clean_key == "enabled") {
                print "Enabled=1"
                has_enabled = 1
                next
            }
            if (clean_key == "allowdllimport") {
                print "AllowDllImport=1"
                has_dll = 1
                next
            }
        }
        print
    }
    END {
        if (in_experts) {
            if (!has_enabled) print "Enabled=1"
            if (!has_dll) print "AllowDllImport=1"
        } else if (!found_experts) {
            print ""
            print "[Experts]"
            print "Enabled=1"
            print "AllowDllImport=1"
        }
    }
    ' FS='=' "$STARTUP_INI" > "$STARTUP_INI.tmp"
    mv "$STARTUP_INI.tmp" "$STARTUP_INI"
fi

# Collect all unique URLs from the environment variable (provided in user config)
declare -A UNIQUE_URLS
FINAL_URLS=""

if [ -n "$WEBREQUEST_URLS" ]; then
    IFS=';,' read -r -a env_urls <<< "$WEBREQUEST_URLS"
    for url in "${env_urls[@]}"; do
        url=$(echo "$url" | xargs)
        if [ -n "$url" ]; then
            # Extract base domain (protocol + host)
            base_url=$(echo "$url" | grep -o -E "https?://[^/\"'\\ \t\r\n]+" || echo "$url")
            UNIQUE_URLS["$base_url"]=1
        fi
    done
    
    # Join keys with semicolon
    for url in "${!UNIQUE_URLS[@]}"; do
        if [ -z "$FINAL_URLS" ]; then
            FINAL_URLS="$url"
        else
            FINAL_URLS="$FINAL_URLS;$url"
        fi
    done
fi

echo "Whitelisted WebRequest URLs: $FINAL_URLS"

# Configure common.ini (UTF-16LE)
COMMON_INI_DIR="${MT5_INSTALL_DIR}/Config"
mkdir -p "$COMMON_INI_DIR"
COMMON_INI="${COMMON_INI_DIR}/common.ini"

if [ ! -f "$COMMON_INI" ]; then
    echo "Creating new default common.ini..."
    cat << 'EOF' > "$COMMON_INI.utf8"
[Common]
[Experts]
AllowDllImport=1
Enabled=1
WebRequest=1
WebRequestUrl=
EOF
else
    echo "Converting existing common.ini to UTF-8 for editing..."
    iconv -f UTF-16LE -t UTF-8 "$COMMON_INI" > "$COMMON_INI.utf8" 2>/dev/null || cp "$COMMON_INI" "$COMMON_INI.utf8"
fi

echo "Updating common.ini with WebRequest whitelists..."
awk -v urls="$FINAL_URLS" '
BEGIN {
    in_experts = 0
    found_experts = 0
    has_webrequest = 0
    has_webrequesturl = 0
    has_enabled = 0
    has_dll = 0
}
/^\[Experts\]/ {
    in_experts = 1
    found_experts = 1
    print
    next
}
/^\[/ && !/^\[Experts\]/ {
    if (in_experts) {
        if (!has_webrequest) print "WebRequest=1"
        if (!has_webrequesturl) print "WebRequestUrl=" urls
        if (!has_enabled) print "Enabled=1"
        if (!has_dll) print "AllowDllImport=1"
        in_experts = 0
    }
    print
    next
}
{
    if (in_experts) {
        clean_key = tolower($1)
        gsub(/[ \t\r\n]/, "", clean_key)
        if (clean_key == "webrequest") {
            print "WebRequest=1"
            has_webrequest = 1
            next
        }
        if (clean_key == "webrequesturl") {
            print "WebRequestUrl=" urls
            has_webrequesturl = 1
            next
        }
        if (clean_key == "enabled") {
            print "Enabled=1"
            has_enabled = 1
            next
        }
        if (clean_key == "allowdllimport") {
            print "AllowDllImport=1"
            has_dll = 1
            next
        }
    }
    print
}
END {
    if (in_experts) {
        if (!has_webrequest) print "WebRequest=1"
        if (!has_webrequesturl) print "WebRequestUrl=" urls
        if (!has_enabled) print "Enabled=1"
        if (!has_dll) print "AllowDllImport=1"
    } else if (!found_experts) {
        print ""
        print "[Experts]"
        print "WebRequest=1"
        print "WebRequestUrl=" urls
        print "Enabled=1"
        print "AllowDllImport=1"
    }
}
' FS='=' "$COMMON_INI.utf8" > "$COMMON_INI.utf8.tmp"

# Convert back to UTF-16LE
iconv -f UTF-8 -t UTF-16LE "$COMMON_INI.utf8.tmp" > "$COMMON_INI"
rm -f "$COMMON_INI.utf8" "$COMMON_INI.utf8.tmp"
echo "common.ini updated successfully."

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
