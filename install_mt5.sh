#!/bin/bash
set -e

# Make sure we are in the directory of the script
cd "$(dirname "$0")"

echo "=== Preparing Wine prefix for MetaTrader 5 ==="
export WINEPREFIX="$HOME/.mt5"

echo "Setting Wine version to Windows 11..."
winecfg -v=win11

echo "Installing Microsoft Edge WebView2 Runtime (silent)..."
if [ -f "webview2.exe" ]; then
    wine webview2.exe /silent /install
else
    echo "webview2.exe not found! Downloading..."
    curl -L "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/f2910a1e-e5a6-4f17-b52d-7faf525d17f8/MicrosoftEdgeWebview2Setup.exe" -o webview2.exe
    wine webview2.exe /silent /install
fi

echo "Launching MetaTrader 5 Installer (silent)..."
if [ -f "mt5setup.exe" ]; then
    wine mt5setup.exe /auto
else
    echo "mt5setup.exe not found! Downloading..."
    curl -L "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" -o mt5setup.exe
    wine mt5setup.exe /auto
fi
