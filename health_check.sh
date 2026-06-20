#!/bin/bash

# Configuration
BOT_TOKEN="8323264961:AAFg5q-dzTCwrWCeYhAOqJNOco8trHY3eJw"
CHAT_ID="-1003908299290"
SERVER_NAME=${1:-$(hostname)}

# Get Stats
# CPU Usage (Calculated as 100% minus the Idle time from vmstat)
CPU_IDLE=$(vmstat 1 2 | tail -n1 | awk '{print $15}')
CPU_USAGE=$(echo "100 - $CPU_IDLE" | bc -l 2>/dev/null || awk "BEGIN {print 100 - $CPU_IDLE}")
# Round CPU usage to 2 decimal places
CPU_USAGE=$(printf "%.2f" "$CPU_USAGE")

# RAM Usage
RAM_TOTAL_MB=$(free -m | awk 'NR==2{print $2}')
RAM_USED_MB=$(free -m | awk 'NR==2{print $3}')
RAM_PCT=$(free -m | awk 'NR==2{printf "%.2f", $3*100/$2}')

# Convert RAM to GB and round to 2 decimal places
RAM_TOTAL_GB=$(awk "BEGIN {printf \"%.2f\", $RAM_TOTAL_MB/1024}")
RAM_USED_GB=$(awk "BEGIN {printf \"%.2f\", $RAM_USED_MB/1024}")

# Disk Usage
DISK_TOTAL=$(df -h / | awk 'NR==2{print $2}')
DISK_USED=$(df -h / | awk 'NR==2{print $3}')
DISK_PCT=$(df -h / | awk 'NR==2{print $5}' | sed 's/%//')

# Build the Message
MESSAGE="⚠️ *Health Check Alert - $SERVER_NAME* ⚠️

🖥️ *CPU Usage:* ${CPU_USAGE}%
💾 *RAM Usage:* ${RAM_PCT}% (${RAM_USED_GB} GB / ${RAM_TOTAL_GB} GB)
💿 *Disk Usage:* ${DISK_PCT}% (${DISK_USED} / ${DISK_TOTAL})"

# Send message to Telegram
curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
     -d "chat_id=${CHAT_ID}" \
     -d "text=${MESSAGE}" \
     -d "parse_mode=Markdown" > /dev/null
