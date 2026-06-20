# Docker Deployment for MT5 ARM64

This document describes how to deploy MetaTrader 5 inside an ARM64-optimized Docker container using Hangover + Xvfb + x11vnc.

## Project Layout on Host
Each instance is kept in `/home/ubuntu/mt5_instances/<instance_name>`:
- `/config`: Mount folder containing `startup.ini`, `tester.ini`, EAs (`.ex5`), and presets (`.set`).
- `/wine_prefix`: Persistent Wine prefix storing broker connection state and DLLs.

## Command Reference

### Local Cross-Compilation (Buildx)
To compile the ARM64 image on a local `x86_64` (Intel/AMD) development machine and push it directly to GitHub Container Registry (GHCR):
```bash
docker buildx build --platform linux/arm64 -t ghcr.io/dixit6054/mt5-hangover:arm64-v1.0 --push .
```
> [!NOTE]
> Since the installation steps for Wine, WebView2, and MT5 have been shifted to container runtime, this build is extremely fast and will not hang or crash under QEMU emulation.

### Manual Execution on VPS
To run the container manually on the target VPS:
```bash
docker run -d --name mt5-test-instance \
  --pid=host \
  -p 127.0.0.1:5900:5900 \
  -v $(pwd)/wine_prefix:/root/.wine \
  -v $(pwd)/config:/etc/mt5/config \
  -e DISPLAY=:99 \
  ghcr.io/dixit6054/mt5-hangover:arm64-v1.0
```

---

## Accessing the Graphical UI (VNC)

The container starts an `x11vnc` server on display `:99` in the background, listening on port `5900` inside the container.

### Secure Connection via SSH Tunnel (Recommended)
By default, the container service maps `5900` to `127.0.0.1:5900` on the host VPS. This prevents unauthorized public access. To connect:
1. Establish a secure SSH tunnel from your local machine:
   ```bash
   ssh -L 5900:localhost:5900 -i "path/to/ssh-key" ubuntu@147.224.213.171
   ```
2. Open your VNC Viewer (e.g., RealVNC Viewer, TigerVNC, or TightVNC) and connect to:
   ```text
   127.0.0.1:5900
   ```
3. Since VNC is run password-less inside the secure tunnel, you will immediately see the virtual desktop containing the running MT5 graphical interface.

---

## Deploying via Coolify

You can manage, auto-restart, and monitor your dockerized MT5 instances using the Coolify panel.

### 1. Accessing Coolify
* **Access URL**: `http://147.224.213.171:8000`
* **Accessing via SSH Tunnel**: If the public port 8000 is blocked by the Oracle Cloud VCN Security List, tunnel it securely:
   ```bash
   ssh -L 8000:localhost:8000 -i "path/to/ssh-key" ubuntu@147.224.213.171
   ```
   Then open `http://localhost:8000` on your browser.

### 2. Creating a Coolify Application
1. In the Coolify dashboard, select **Projects** -> **Create Project** -> **Production**.
2. Click **Add New Resource** -> **Docker Image**.
3. Fill in the image name:
   ```text
   ghcr.io/dixit6054/mt5-hangover:arm64-v1.0
   ```
4. Under **Configuration**:
   * **Custom Docker Arguments**: Add `--pid=host` (important for the host process monitor script `mt5_monitor.sh` to track execution metrics).
   * **Environment Variables**: Add `DISPLAY=:99`.
5. Under **Ports**:
   * Expose port `5900` for VNC graphical checking.
6. Under **Volumes / Mounts**, add the following bind mounts:
   ```text
   /home/ubuntu/mt5_instances/mt5_second_account/wine_prefix:/root/.wine
   /home/ubuntu/mt5_instances/mt5_second_account/config:/etc/mt5/config
   ```

---

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

### Graphical Diagnostics (X11 forwarding)
If running outside a VNC setup and you want to forward graphics directly to your local display:
1. Share the X11 socket: `-v /tmp/.X11-unix:/tmp/.X11-unix`
2. Grant access on the host: `xhost +local:root`


