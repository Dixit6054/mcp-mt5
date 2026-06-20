# Docker Deployment for MT5 ARM64

This document describes how to deploy MetaTrader 5 inside an ARM64-optimized Docker container using Hangover + X11.

## Project Layout on Host
Each instance is kept in `/home/ubuntu/mt5_instances/<instance_name>`:
- `/config`: Mount folder containing `startup.ini`, `tester.ini`, EAs (`.ex5`), and presets (`.set`).
- `/wine_prefix`: Persistent Wine prefix storing broker connection state and DLLs.
- `/logs`: Directory where terminal application logs are stored.
- `/mql5_logs`: Directory where Expert Advisor execution logs are stored.

## Command Reference

### Manual Build
```bash
docker build -t ghcr.io/dixit6054/mt5-hangover:arm64-v1.0 .
```

### Manual Execution
```bash
docker run -d --name mt5-test-instance \
  --pid=host \
  -v $(pwd)/wine_prefix:/root/.wine \
  -v $(pwd)/config:/etc/mt5/config \
  -v $(pwd)/logs:/root/.wine/drive_c/Program\ Files/MetaTrader\ 5/logs \
  -v $(pwd)/mql5_logs:/root/.wine/drive_c/Program\ Files/MetaTrader\ 5/MQL5/Logs \
  -e DISPLAY=:99 \
  ghcr.io/dixit6054/mt5-hangover:arm64-v1.0
```

## Deploying via Coolify

You can manage and monitor your dockerized MT5 instances using the newly installed Coolify panel on the VPS.

### 1. Accessing Coolify
* **Access URL**: `http://147.224.213.171:8000`
* **Accessing via SSH Tunnel (Recommended)**: If the public port 8000 is blocked by the Oracle Cloud VCN Security List, you can tunnel it securely from your local terminal:
  ```bash
  ssh -L 8000:localhost:8000 -i "path/to/ssh-key" ubuntu@147.224.213.171
  ```
  Then navigate to `http://localhost:8000` on your local browser.

### 2. Creating a Coolify Application
1. In the Coolify dashboard, select **Projects** -> **Create Project** -> **Production**.
2. Click **Add New Resource** -> **Docker Image**.
3. Fill in the image name:
   ```text
   ghcr.io/dixit6054/mt5-hangover:arm64-v1.0
   ```
4. Under **Configuration**:
   * **Custom Docker Arguments**: Add `--pid=host` to ensure the host process monitoring script (`mt5_monitor.sh`) can dynamically track memory, accounts, and connections.
   * **Environment Variables**: Add `DISPLAY=:99`.
5. Under **Volumes / Mounts**, add the following bind mounts:
   ```text
   /home/ubuntu/mt5_instances/mt5_second_account/wine_prefix:/root/.wine
   /home/ubuntu/mt5_instances/mt5_second_account/config:/etc/mt5/config
   ```

## Troubleshooting

### Wine Prefix Issues (Ownership / Security)
If you encounter `wine: '/root/.wine' is not owned by you` errors:
1. This is a Wine security check when host directories are bind-mounted with incorrect host UIDs.
2. The `entrypoint.sh` automatically runs `chown -R root:root /root/.wine` at startup to correct this. Ensure the container has root capabilities.
3. If resetting is needed:
   * Stop the systemd service or Coolify application.
   * Empty the `/home/ubuntu/mt5_instances/<instance_name>/wine_prefix` directory.
   * Re-seed the prefix from your legacy folder:
     ```bash
     cp -r ~/.mt5/* /home/ubuntu/mt5_instances/<instance_name>/wine_prefix/
     ```
   * Start the service.

### X11 Socket & Graphical Debugging
To allow the container to connect to the host's X11 server for graphical debugging:
1. Share the X11 socket: `-v /tmp/.X11-unix:/tmp/.X11-unix`
2. Grant access on the host: `xhost +local:root`

