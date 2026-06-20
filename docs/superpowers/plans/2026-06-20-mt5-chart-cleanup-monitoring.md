# MT5 Headless Chart Management & Bash Telegram Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up charts on headless deployments to only show the chart with the attached EA, and deploy an hourly Bash monitoring script that reports active MT5 terminals to Telegram.

**Architecture:** 
1. Modify `remote_deploy.py` to:
   - Delete default charts (`rm -f .../Profiles/Charts/Default/*.chr`) on the remote instance before starting the terminal.
   - Inject the `Expert` keys in `startup.ini` under the `[Experts]` section so MT5 automatically opens the designated chart and attaches the EA on startup.
2. Develop a Bash script `mt5_monitor.sh` on the remote VPS to:
   - Search for running `terminal64.exe` PIDs.
   - Resolve their respective installation paths via `/proc/<pid>/maps`.
   - Read and decode their UTF-16 config (`common.ini`) and chart (`chart*.chr`) files to extract Login, Broker, and attached EAs.
   - Measure memory usage from `/proc/<pid>/status`.
   - Send an hourly report to Telegram via `curl` and configure it under cron.

**Tech Stack:** Python (local deployer changes), Bash, Linux `/proc` filesystem, GNU `iconv`, `curl`, and Telegram Bot API.

## Global Constraints
- Target VPS: Oracle VM (`147.224.213.171`)
- User: `ubuntu`
- SSH Key: `C:/Users/dixit/Desktop/mt5 antigravity/ssh-key-2026-06-19 (1).key`
- Telegram Bot Token: `8323264961:AAFg5q-dzTCwrWCeYhAOqJNOco8trHY3eJw`
- Telegram Chat ID: `-1003908299290`

---

## Proposed Changes & Tasks

### Task 1: Update `remote_deploy.py` for Chart Cleanup and Native EA Attachment

**Files:**
- Modify: `mcp_server_code/src/mcp_mt5/remote_deploy.py`

**Interfaces:**
- Consumes: None (Updates existing function `deploy_remote_instance`).
- Produces: Enhanced `deploy_remote_instance` function that performs chart cleanup and configures startup EA attachment.

- [ ] **Step 1: Write the tests or identify what to modify**
  We will modify the `deploy_remote_instance` function to:
  1. Add a step after cloning the base prefix to run `rm -f <target_prefix>/drive_c/Program\ Files/MetaTrader\ 5/Profiles/Charts/Default/*.chr`.
  2. Modify the generated `startup.ini` to support launching an EA. We will update the `[Experts]` section of `startup.ini` to:
     ```ini
     [Experts]
     AllowDllImport=1
     Enabled=1
     Expert=Experts\<EA_Name>
     Symbol=<Symbol>
     Period=H1
     ```
     where `<EA_Name>` is extracted from `ea_local_path` (if provided).

- [ ] **Step 2: Edit `remote_deploy.py`**
  Modify [remote_deploy.py](file:///c:/Users/dixit/Desktop/mt5%20antigravity/mcp_server_code/src/mcp_mt5/remote_deploy.py):
  - In section 2 (Clone Base Prefix), add:
    ```python
    # Clean up default charts so only the designated chart opens
    run_ssh(f"rm -f {target_prefix}/drive_c/Program\\ Files/MetaTrader\\ 5/Profiles/Charts/Default/*.chr")
    ```
  - In section 4 (Generate startup config.ini), if `ea_local_path` is provided, parse the EA name and inject it into the `[Experts]` section as:
    ```ini
    Expert=Experts/{ea_name}
    Symbol={symbol}
    Period=H1
    ```
    If `preset_local_path` is provided, parse the preset name and inject:
    ```ini
    ExpertParameters=Presets/{preset_name}
    ```

- [ ] **Step 3: Verify local syntax and changes**
  Run syntax check: `python -m py_compile mcp_server_code/src/mcp_mt5/remote_deploy.py`
  Expected: Successful compilation without syntax errors.

---

### Task 2: Create Bash Monitoring Script (`mt5_monitor.sh`)

**Files:**
- Create: `mt5_monitor.sh` (to be written locally and uploaded to `/home/ubuntu/scripts/mt5_monitor.sh` on the VPS)

**Interfaces:**
- Consumes: None (independent monitoring script).
- Produces: `/home/ubuntu/scripts/mt5_monitor.sh` script on the VPS.

- [ ] **Step 1: Write `mt5_monitor.sh` locally**
  Create the script content:
  ```bash
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
          # Skip xrdp wrapper process if it contains terminal64 in string but is not wine
          if ! grep -q "wine" "/proc/$pid/cmdline" 2>/dev/null && ! grep -q "terminal64.exe" "/proc/$pid/cmdline" 2>/dev/null; then
              continue
          fi
          
          # Memory Usage
          mem_kb=$(grep -s VmRSS "/proc/$pid/status" | awk '{print $2}')
          mem_mb=$((mem_kb / 1024))
          
          # Path resolution via maps
          mt5_path=$(grep -o -m 1 -a '/home/ubuntu/[^/]*\/drive_c\/Program Files\/MetaTrader 5' /proc/$pid/maps | head -n 1)
          if [ -z "$mt5_path" ]; then
              mt5_path="/home/ubuntu/.mt5/drive_c/Program Files/MetaTrader 5"
          fi
          
          instance_name=$(echo "$mt5_path" | cut -d'/' -f4)
          
          # Parse common.ini (UTF-16 LE)
          login="Unknown"
          server="Unknown"
          profile="Default"
          
          if [ -f "$mt5_path/Config/common.ini" ]; then
              common_utf8=$(iconv -f UTF-16LE -t UTF-8 "$mt5_path/Config/common.ini" 2>/dev/null)
              login=$(echo "$common_utf8" | grep -i "^Login=" | cut -d'=' -f2 | tr -d '\r')
              server=$(echo "$common_utf8" | grep -i "^Server=" | cut -d'=' -f2 | tr -d '\r')
              profile=$(echo "$common_utf8" | grep -i "^ProfileLast=" | cut -d'=' -f2 | tr -d '\r')
          fi
          
          [ -z "$profile" ] && profile="Default"
          
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
          
          MESSAGE="$MESSAGE
  🔹 *Instance:* $instance_name (PID: $pid)
     • *Account:* $login
     • *Broker:* $server
     • *Memory:* ${mem_mb} MB
     • *EAs:* $ea_list
  "
      done
  fi
  
  # Send to Telegram
  curl -s -X POST "https://api.telegram.org/bot\${BOT_TOKEN}/sendMessage" \
       -d "chat_id=\${CHAT_ID}" \
       -d "text=\${MESSAGE}" \
       -d "parse_mode=Markdown" > /dev/null
  ```

- [ ] **Step 2: Upload `mt5_monitor.sh` to the VPS**
  Use SCP to copy the script:
  `scp -i "C:/Users/dixit/Desktop/mt5 antigravity/ssh-key-2026-06-19 (1).key" -o StrictHostKeyChecking=no mt5_monitor.sh ubuntu@147.224.213.171:/home/ubuntu/scripts/mt5_monitor.sh`

- [ ] **Step 3: Make it executable on the VPS**
  SSH command:
  `ssh -i "C:/Users/dixit/Desktop/mt5 antigravity/ssh-key-2026-06-19 (1).key" ubuntu@147.224.213.171 "chmod +x /home/ubuntu/scripts/mt5_monitor.sh"`

- [ ] **Step 4: Manually test the script on the VPS**
  SSH command:
  `ssh -i "C:/Users/dixit/Desktop/mt5 antigravity/ssh-key-2026-06-19 (1).key" ubuntu@147.224.213.171 "/home/ubuntu/scripts/mt5_monitor.sh"`
  Expected: A message is sent to the Telegram channel containing the two active MT5 instances (base and second account) with their details.

---

### Task 3: Schedule Monitoring Script via Cron

**Files:**
- Modify: crontab on remote VPS

**Interfaces:**
- Consumes: `/home/ubuntu/scripts/mt5_monitor.sh`
- Produces: Hourly execution schedule.

- [ ] **Step 1: Check existing cron jobs on VPS**
  SSH command:
  `ssh -i "C:/Users/dixit/Desktop/mt5 antigravity/ssh-key-2026-06-19 (1).key" ubuntu@147.224.213.171 "crontab -l"`

- [ ] **Step 2: Add hourly monitoring cron job**
  Add the following line to crontab:
  `0 * * * * /home/ubuntu/scripts/mt5_monitor.sh`
  We can do this via an SSH one-liner:
  `ssh -i "C:/Users/dixit/Desktop/mt5 antigravity/ssh-key-2026-06-19 (1).key" ubuntu@147.224.213.171 "(crontab -l 2>/dev/null; echo '0 * * * * /home/ubuntu/scripts/mt5_monitor.sh') | crontab -"`

- [ ] **Step 3: Verify crontab updated successfully**
  SSH command:
  `ssh -i "C:/Users/dixit/Desktop/mt5 antigravity/ssh-key-2026-06-19 (1).key" ubuntu@147.224.213.171 "crontab -l"`
  Expected: The hourly cron job is listed in the output.
