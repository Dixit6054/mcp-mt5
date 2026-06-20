#!/bin/bash

# Configuration
BOT_TOKEN="8323264961:AAFg5q-dzTCwrWCeYhAOqJNOco8trHY3eJw"
CHAT_ID="-1003908299290"

# Get running terminal64 PIDs
pids=$(pgrep -f "terminal64.exe")

if [ -z "$pids" ]; then
    MESSAGE="⚠️ *MT5 Monitor Alert* ⚠️

No running MT5 instances found on $(hostname)."
else
    MESSAGE="📊 *MT5 Instances Breakdown - $(hostname)* 📊
"
    for pid in $pids; do
        # Only process if maps file contains terminal64.exe (filters out bash wrappers like xvfb-run)
        if ! grep -q "terminal64.exe" "/proc/$pid/maps" 2>/dev/null; then
            continue
        fi
        
        # Memory Usage
        mem_kb=$(grep -s VmRSS "/proc/$pid/status" | awk '{print $2}')
        mem_mb=$((mem_kb / 1024))
        
        # Path resolution via maps
        mt5_path=$(grep -o -m 1 -a '/home/ubuntu/[^/]*\/drive_c\/Program Files\/MetaTrader 5' /proc/$pid/maps | head -n 1)
        if [ -z "$mt5_path" ]; then
            # If not found via maps, try default paths
            if [ -d "/home/ubuntu/.mt5/drive_c/Program Files/MetaTrader 5" ]; then
                mt5_path="/home/ubuntu/.mt5/drive_c/Program Files/MetaTrader 5"
            else
                continue
            fi
        fi
        
        # Extract instance name from path (e.g. .mt5_second_account)
        instance_name=$(echo "$mt5_path" | cut -d'/' -f4)
        
        # Parse today's terminal log and isolate lines from the current run
        latest_term_log=$(ls -t "$mt5_path/logs"/*.log 2>/dev/null | head -n 1)
        log_content=""
        current_run_logs=""
        if [ -n "$latest_term_log" ]; then
            log_content=$(iconv -f UTF-16LE -t UTF-8 "$latest_term_log" 2>/dev/null)
            # Find the line number of the last startup header
            start_line_num=$(echo "$log_content" | grep -nEi "started for|launched with" | tail -n 1 | cut -d':' -f1)
            if [ -n "$start_line_num" ]; then
                current_run_logs=$(echo "$log_content" | tail -n +"$start_line_num")
            else
                current_run_logs="$log_content"
            fi
        fi
        
        # Resolve active login/account and broker/server dynamically
        login="Unknown"
        server="Unknown"
        
        # 1. Try to parse from the current run's log lines
        if [ -n "$current_run_logs" ]; then
            login=$(echo "$current_run_logs" | grep -o -E "'[0-9]+': (authorized|synchronized|trading has been enabled|auto connecting|connection|failed)" | tail -n 1 | grep -o -E "[0-9]+")
            server=$(echo "$current_run_logs" | grep -o -E "authorized on [a-zA-Z0-9_-]+" | tail -n 1 | cut -d' ' -f3)
        fi
        
        # 2. If still Unknown, try startup.ini in drive_c or MetaTrader 5 directory
        if [ -z "$login" ] || [ "$login" = "Unknown" ] || [ -z "$server" ] || [ "$server" = "Unknown" ]; then
            if [ -f "$mt5_path/startup.ini" ]; then
                [ -z "$login" ] || [ "$login" = "Unknown" ] && login=$(grep -i "^Login=" "$mt5_path/startup.ini" | cut -d'=' -f2 | tr -d '\r')
                [ -z "$server" ] || [ "$server" = "Unknown" ] && server=$(grep -i "^Server=" "$mt5_path/startup.ini" | cut -d'=' -f2 | tr -d '\r')
            elif [ -f "$mt5_path/../../startup.ini" ]; then
                [ -z "$login" ] || [ "$login" = "Unknown" ] && login=$(grep -i "^Login=" "$mt5_path/../../startup.ini" | cut -d'=' -f2 | tr -d '\r')
                [ -z "$server" ] || [ "$server" = "Unknown" ] && server=$(grep -i "^Server=" "$mt5_path/../../startup.ini" | cut -d'=' -f2 | tr -d '\r')
            fi
        fi
        
        # 3. If still Unknown, fall back to common.ini
        if [ -z "$login" ] || [ "$login" = "Unknown" ] || [ -z "$server" ] || [ "$server" = "Unknown" ]; then
            if [ -f "$mt5_path/Config/common.ini" ]; then
                common_utf8=$(iconv -f UTF-16LE -t UTF-8 "$mt5_path/Config/common.ini" 2>/dev/null)
                [ -z "$login" ] || [ "$login" = "Unknown" ] && login=$(echo "$common_utf8" | grep -i "^Login=" | cut -d'=' -f2 | tr -d '\r')
                [ -z "$server" ] || [ "$server" = "Unknown" ] && server=$(echo "$common_utf8" | grep -i "^Server=" | cut -d'=' -f2 | tr -d '\r')
            fi
        fi
        
        [ -z "$login" ] && login="Unknown"
        [ -z "$server" ] && server="Unknown"
        
        # Resolve profile name for active chart check
        profile="Default"
        if [ -f "$mt5_path/Config/common.ini" ]; then
            common_utf8=$(iconv -f UTF-16LE -t UTF-8 "$mt5_path/Config/common.ini" 2>/dev/null)
            profile=$(echo "$common_utf8" | grep -i "^ProfileLast=" | cut -d'=' -f2 | tr -d '\r')
        fi
        [ -z "$profile" ] && profile="Default"
        
        # Determine connection status
        conn_status="Unknown"
        
        # Check active TCP connections using sudo ss matching process PID
        tcp_conn=$(sudo ss -t -p -n 2>/dev/null | grep -E "pid=$pid\b" | grep -E "ESTAB")
        
        if [ -n "$tcp_conn" ]; then
            conn_status="Online (Connected)"
        else
            # Fall back to logs if no TCP socket is found
            if [ -n "$current_run_logs" ]; then
                last_conn_line=$(echo "$current_run_logs" | grep -Ei "authorized|synchronized|connection|disconnect|failed|trading has been enabled" | tail -n 1)
                
                if [ -n "$last_conn_line" ]; then
                    if echo "$last_conn_line" | grep -qi "authorized\|synchronized\|trading has been enabled"; then
                        conn_status="Online (Connected)"
                    elif echo "$last_conn_line" | grep -qi "failed\|invalid account"; then
                        conn_status="Authorization Failed"
                    elif echo "$last_conn_line" | grep -qi "no connection\|disconnected"; then
                        conn_status="Offline (Disconnected)"
                    else
                        conn_status="Status: $(echo "$last_conn_line" | awk -F'\t' '{print $NF}')"
                    fi
                else
                    conn_status="Offline (No Connection)"
                fi
            else
                conn_status="Offline (No logs)"
            fi
        fi
        
        # Find Attached EAs in the active profile's charts
        ea_list=""
        charts_dir="$mt5_path/Profiles/Charts/$profile"
        if [ -d "$charts_dir" ]; then
            for chr_file in "$charts_dir"/chart*.chr; do
                if [ -f "$chr_file" ]; then
                    chr_utf8=$(iconv -f UTF-16LE -t UTF-8 "$chr_file" 2>/dev/null)
                    if echo "$chr_utf8" | grep -q "<expert>"; then
                        symbol=$(echo "$chr_utf8" | grep -i "^symbol=" | cut -d'=' -f2 | tr -d '\r')
                        ea_name=$(echo "$chr_utf8" | awk '/<expert>/{flag=1;next}/<\/expert>/{flag=0} flag' | grep -i "^name=" | cut -d'=' -f2 | tr -d '\r')
                        if [ -n "$ea_name" ]; then
                            if [ -n "$ea_list" ]; then
                                ea_list="$ea_list, $ea_name ($symbol)"
                            else
                                ea_list="$ea_name ($symbol)"
                            fi
                        fi
                    fi
                fi
            done
        fi
        
        [ -z "$ea_list" ] && ea_list="None"
        
        # Filter terminal errors from the last 1 hour
        term_errs=""
        if [ -n "$current_run_logs" ]; then
            now_sec=$((10#$(date -u +%H) * 3600 + 10#$(date -u +%M) * 60 + 10#$(date -u +%S)))
            term_errs=$(echo "$current_run_logs" | grep -Ei "error|failed|rejected|refused|limit" | awk -F'\t' -v now="$now_sec" '
            {
                time_str = ""
                for (i = 1; i <= NF; i++) {
                    if ($i ~ /^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]/) {
                        time_str = $i
                        break
                    }
                }
                if (time_str != "" && split(time_str, parts, ":") == 3) {
                    h = parts[1] + 0
                    m = parts[2] + 0
                    s = parts[3] + 0
                    line_sec = h * 3600 + m * 60 + s
                    diff = now - line_sec
                    if (diff < 0) diff += 86400
                    if (diff <= 3600) {
                        print $0
                    }
                }
            }')
        fi
        
        # Filter Expert Advisor errors from the last 1 hour
        mql_errs=""
        latest_mql_log=$(ls -t "$mt5_path/MQL5/logs"/*.log 2>/dev/null | head -n 1)
        if [ -n "$latest_mql_log" ]; then
            mql_content=$(iconv -f UTF-16LE -t UTF-8 "$latest_mql_log" 2>/dev/null)
            now_sec=$((10#$(date -u +%H) * 3600 + 10#$(date -u +%M) * 60 + 10#$(date -u +%S)))
            mql_errs=$(echo "$mql_content" | grep -Ei "error|failed|critical|stopped|zero" | awk -F'\t' -v now="$now_sec" '
            {
                time_str = ""
                for (i = 1; i <= NF; i++) {
                    if ($i ~ /^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]/) {
                        time_str = $i
                        break
                    }
                }
                if (time_str != "" && split(time_str, parts, ":") == 3) {
                    h = parts[1] + 0
                    m = parts[2] + 0
                    s = parts[3] + 0
                    line_sec = h * 3600 + m * 60 + s
                    diff = now - line_sec
                    if (diff < 0) diff += 86400
                    if (diff <= 3600) {
                        print $0
                    }
                }
            }')
        fi
        
        err_msg=""
        if [ -n "$term_errs" ]; then
            formatted_errs=$(echo "$term_errs" | tr -d '\r' | sed 's/^/      • /' | tail -n 5)
            err_msg="   • *Recent Journal Errors (Last 1h):*
$formatted_errs"
        fi
        
        if [ -n "$mql_errs" ]; then
            formatted_mql_errs=$(echo "$mql_errs" | tr -d '\r' | sed 's/^/      • /' | tail -n 5)
            if [ -n "$err_msg" ]; then
                err_msg="$err_msg
   • *Recent Expert Errors (Last 1h):*
$formatted_mql_errs"
            else
                err_msg="   • *Recent Expert Errors (Last 1h):*
$formatted_mql_errs"
            fi
        fi
        
        MESSAGE="$MESSAGE
🔹 *Instance:* \`$instance_name\` (PID: $pid)
   • *Account:* \`$login\`
   • *Broker:* \`$server\`
   • *Status:* $conn_status
   • *Memory:* ${mem_mb} MB
   • *EAs:* \`$ea_list\`"

        if [ -n "$err_msg" ]; then
            MESSAGE="$MESSAGE
$err_msg"
        fi
        MESSAGE="$MESSAGE
"
    done
fi

# Send to Telegram
curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
     -d "chat_id=${CHAT_ID}" \
     --data-urlencode "text=${MESSAGE}" \
     -d "parse_mode=Markdown" > /dev/null
