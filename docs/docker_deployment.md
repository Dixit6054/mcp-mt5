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

## Troubleshooting

### Wine Prefix Issues
If you encounter broker authentication problems or database corruption:
1. Stop the instance: `sudo systemctl stop mt5_instance_name` (or `docker stop mt5_instance_name`).
2. Clear the contents of `/home/ubuntu/mt5_instances/<instance_name>/wine_prefix` (keep it clean or copy a valid working template ~/.mt5).
3. Restart the service: `sudo systemctl start mt5_instance_name`.

### X11 socket
To allow the container to connect to the host's X11 server for graphical debugging:
1. Share the X11 socket: `-v /tmp/.X11-unix:/tmp/.X11-unix`
2. Grant access: `xhost +local:root` on the host.
