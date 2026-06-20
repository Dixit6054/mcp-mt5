# Remote Deployment & Monitoring Guide

This document covers the infrastructure components built around `mcp-mt5` for executing headless MetaTrader 5 deployments, observability, and server health checks on remote Linux VPS instances using Wine.

## 1. Remote Headless MT5 Deployment

The `remote_deploy.py` script orchestrates the deployment of MT5 terminal instances to remote servers. It handles local compilation of MQL code and remote distribution via SCP.

### Key Deployment Steps
1. **Packaging:** The local EA code and preset (`.set`) files are copied or compiled.
2. **Path Generation:** The script dynamically provisions an isolated directory on the remote host (e.g., `~/.mt5_second_account`).
3. **Execution configuration (`startup.ini`):** Required Windows-style paths for the terminal are properly escaped with double-backslashes (e.g., `/config:C:\\startup.ini`) so that they correctly resolve inside the Wine layer on the target server.
4. **Persistent systemd user service:** A user-level systemd service is dynamically generated (`mt5_second_account.service`), ensuring that the headless terminal persists across sessions and reboots.
5. **Data Structure:** The script guarantees that required `Experts` and `Presets` subdirectories are explicitly created on the remote side before secure copying the `.ex5` and `.set` files.

---

## 2. MT5 Terminal Observability

Headless MT5 terminals provide zero UI visibility. To gain insight into what happens at runtime, we deploy the `mt5_monitor.sh` script to parse logs and send alerts to Telegram.

### `mt5_monitor.sh` Architecture
- **Dynamic Terminal Discovery:** Rather than hardcoding paths, the script lists all `terminal64.exe` processes and uses `grep -o -a` on `/proc/[PID]/maps` to find exactly where the `MQL5` folder is mapped for each active instance.
- **Account Identification:** It reads `accounts.dat` or `servers.dat` (depending on the internal setup) to retrieve the active MT5 Account ID and Broker Name.
- **Error Scraping:** The script checks the recent hourly logs inside `MQL5/Logs` and `MQL5/Experts/Logs` to pull out errors, failed EA attachments, or `tester.ini` validation problems.
- **Delivery:** Sends a beautifully formatted Markdown alert directly to the pre-configured Telegram Chat ID.

### Cron Scheduling
To keep observability near real-time, the monitor runs as an hourly cron job on the remote server:
```bash
0 * * * * /home/ubuntu/scripts/mt5_monitor.sh
```

---

## 3. Server Health Checking

Along with MT5-level logging, we operate `health_check.sh` on our remote VPS instances (e.g., Oracle, GCP) to track the underlying system resource utilization.

### `health_check.sh` Metrics
- **CPU Usage:** Computed inversely using the Idle Time from `vmstat`.
- **RAM Usage:** Pulled via `free -m`, calculated as used percentage alongside total GB available.
- **Disk Space:** Validates that log bloat hasn't filled the root partition `/`, reporting free space via `df -h`.

### Cron Scheduling
The script requires the Server Name parameter passed to identify which VPS triggered the alert. This is configured in the crontab:
```bash
# Oracle VPS Health Check
0 * * * * /home/ubuntu/scripts/health_check.sh "Oracle VPS"

# GCP VPS Health Check
0 * * * * /home/dixit/scripts/health_check.sh "GCP VPS"
```

---

## 4. Maintenance & Cleanup Best Practices

During headless operations, MT5 activates default services that provide unnecessary overhead and noise in logs.

### Removing `BalanceWriter`
The automated deployments strip out the default `BalanceWriter` service, as it creates rapid write operations (e.g., `stats.txt`) that are unneeded for simple EA execution and could impact VPS I/O. If you notice `BalanceWriter` running manually:
- Terminate the active MT5 `systemd` service.
- Delete the `BalanceWriter.*` files inside `MQL5/Services/`.
- Restart the terminal.
