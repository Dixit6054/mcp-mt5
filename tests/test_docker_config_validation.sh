#!/bin/bash
# Test config validator locally

# Setup temp config dir
TEMP_CONFIG=$(mktemp -d)

# Test 1: Missing startup.ini
if ./config-validator.sh 2>&1 | grep -q "ERROR: startup.ini not found"; then
    echo "Pass: validator rejects missing startup.ini"
else
    echo "Fail: validator did not reject missing startup.ini"
    exit 1
fi

# Test 2: Incomplete startup.ini
mkdir -p "${TEMP_CONFIG}"
echo -e "[Common]\nLogin=123" > "${TEMP_CONFIG}/startup.ini"

export CONFIG_DIR="${TEMP_CONFIG}"
# Temporarily override script config path for testing
sed 's|CONFIG_DIR="/etc/mt5/config"|CONFIG_DIR="'${TEMP_CONFIG}'"|' config-validator.sh > temp_val.sh
chmod +x temp_val.sh

if ./temp_val.sh 2>&1 | grep -q "ERROR: 'Password' parameter is missing"; then
    echo "Pass: validator rejects missing parameters"
else
    echo "Fail: validator did not reject missing parameters"
    rm -rf "${TEMP_CONFIG}" temp_val.sh
    exit 1
fi

# Test 3: Complete startup.ini
echo -e "[Common]\nLogin=123\nPassword=456\nServer=789" > "${TEMP_CONFIG}/startup.ini"
if ./temp_val.sh 2>&1 | grep -q "Configuration validation successful"; then
    echo "Pass: validator accepts correct startup.ini"
else
    echo "Fail: validator did not accept correct startup.ini"
    rm -rf "${TEMP_CONFIG}" temp_val.sh
    exit 1
fi

rm -rf "${TEMP_CONFIG}" temp_val.sh
echo "All integration tests for validator passed!"
