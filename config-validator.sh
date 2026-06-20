#!/bin/bash
set -e

CONFIG_DIR="/etc/mt5/config"
STARTUP_INI="${CONFIG_DIR}/startup.ini"

if [ ! -f "$STARTUP_INI" ]; then
    echo "ERROR: startup.ini not found in ${CONFIG_DIR}."
    exit 1
fi

# Basic validation
if ! grep -q -i "^Login=" "$STARTUP_INI"; then
    echo "ERROR: 'Login' parameter is missing in startup.ini."
    exit 1
fi

if ! grep -q -i "^Password=" "$STARTUP_INI"; then
    echo "WARNING: 'Password' parameter is missing in startup.ini (this is fine if using a seeded wine prefix)."
fi

if ! grep -q -i "^Server=" "$STARTUP_INI"; then
    echo "ERROR: 'Server' parameter is missing in startup.ini."
    exit 1
fi

echo "Configuration validation successful."
