# Dockerize mcp-mt5 for ARM64 Hangover + X11 Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a production-ready, ARM64-optimized Docker container containing MetaTrader 5 (MT5) running via Hangover with headless Xvfb support, allowing config injection and persistence at runtime, integrated with systemd and remote_deploy.py.

**Architecture:** Use a multi-stage Docker build to package Ubuntu 24.04, the official stable Hangover release (v11.9), and the MT5 binary. At runtime, configs are bind-mounted and MT5 runs in Portable Mode (`/portable`) with the Wine prefix persisted in a mapped volume.

**Tech Stack:** Docker, Ubuntu 24.04 (ARM64), Hangover (Wine 11.9), Xvfb, Bash, Python, Systemd.

## Global Constraints
- Target Architecture: ARM64 (`linux/arm64`) only.
- Base OS: Ubuntu 24.04 (Noble).
- Hangover Version: Stable official release `hangover-11.9`.
- Production-Only: No Python or `mcp-mt5` server components inside the runtime container.

---

### Task 1: Dockerfile & Base Setup

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `config-validator.sh`
- Create: `entrypoint.sh`

**Interfaces:**
- Consumes: None (starting foundation)
- Produces: Base Docker image `ghcr.io/dixit6054/mt5-hangover:arm64-v1.0`

- [ ] **Step 1: Create the `.dockerignore` file**
  Create `.dockerignore` at the root of the project to exclude local python environments and caches from the build context.
  
  ```
  .git
  .venv
  __pycache__
  *.pyc
  docs/
  tests/
  mcp_server_code/
  ```

- [ ] **Step 2: Create the `config-validator.sh` file**
  Write a lightweight validation script that verifies `/etc/mt5/config/startup.ini` exists and contains basic MT5 parameters.
  
  ```bash
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
      echo "ERROR: 'Password' parameter is missing in startup.ini."
      exit 1
  fi

  if ! grep -q -i "^Server=" "$STARTUP_INI"; then
      echo "ERROR: 'Server' parameter is missing in startup.ini."
      exit 1
  fi

  echo "Configuration validation successful."
  ```

- [ ] **Step 3: Create the `entrypoint.sh` file**
  Write a bash script that handles starting Xvfb, validating configs, mounting EAs/presets, launching MT5 in portable mode, and handling termination signals gracefully.
  
  ```bash
  #!/bin/bash
  set -e

  # 1. Start Xvfb in background
  echo "Starting Xvfb on DISPLAY ${DISPLAY}..."
  rm -f /tmp/.X99-lock
  Xvfb ${DISPLAY} -screen 0 1024x768x16 &
  XVFB_PID=$!
  sleep 2

  # 2. Run config validator
  echo "Validating configuration files..."
  /usr/local/bin/config-validator.sh

  # 3. Mount files to the portable directories
  MT5_INSTALL_DIR="/root/.wine/drive_c/Program Files/MetaTrader 5"
  CONFIG_DIR="/etc/mt5/config"

  echo "Copying config files and EA/presets..."
  mkdir -p "${MT5_INSTALL_DIR}/MQL5/Experts"
  mkdir -p "${MT5_INSTALL_DIR}/MQL5/Presets"

  # Copy startup.ini to drive_c
  if [ -f "${CONFIG_DIR}/startup.ini" ]; then
      cp "${CONFIG_DIR}/startup.ini" "/root/.wine/drive_c/startup.ini"
  fi

  # Copy EA binaries if present
  if ls "${CONFIG_DIR}"/*.ex5 >/dev/null 2>&1; then
      cp "${CONFIG_DIR}"/*.ex5 "${MT5_INSTALL_DIR}/MQL5/Experts/"
  fi

  # Copy presets if present
  if ls "${CONFIG_DIR}"/*.set >/dev/null 2>&1; then
      cp "${CONFIG_DIR}"/*.set "${MT5_INSTALL_DIR}/MQL5/Presets/"
  fi

  # 4. Handle exit signals for graceful termination
  cleanup() {
      echo "Stopping MetaTrader 5..."
      wineserver -k || true
      echo "Stopping Xvfb..."
      kill $XVFB_PID || true
      exit 0
  }
  trap cleanup SIGTERM SIGINT

  # 5. Launch MT5 Terminal in portable mode
  echo "Launching MT5 Terminal in portable mode..."
  WINEDLLOVERRIDES="mscoree,mshtml=" wine "${MT5_INSTALL_DIR}/terminal64.exe" /portable /config:C:\\startup.ini &
  MT5_PID=$!

  wait $MT5_PID
  ```

- [ ] **Step 4: Create the `Dockerfile`**
  Write the multi-stage Dockerfile that fetches Hangover and configures Wine/MT5.
  
  ```dockerfile
  # Stage 1: Download and unpack Hangover
  FROM ubuntu:24.04 AS hangover-builder
  ENV DEBIAN_FRONTEND=noninteractive
  RUN apt-get update && apt-get install -y curl tar
  WORKDIR /opt
  RUN curl -L -O https://github.com/AndreRH/hangover/releases/download/hangover-11.9/hangover_11.9_ubuntu2404_noble_arm64.tar && \
      tar -xf hangover_11.9_ubuntu2404_noble_arm64.tar && \
      rm hangover_11.9_ubuntu2404_noble_arm64.tar

  # Stage 2: Final image
  FROM ubuntu:24.04
  ENV DEBIAN_FRONTEND=noninteractive

  # Install base packages (Note: libasound2t64 is for Ubuntu 24.04)
  RUN apt-get update && apt-get install -y \
      xvfb \
      x11-apps \
      xauth \
      ca-certificates \
      curl \
      libasound2t64 \
      libpulse0 \
      && rm -rf /var/lib/apt/lists/*

  # Copy Hangover
  COPY --from=hangover-builder /opt/hangover /opt/hangover

  # Set up symlinks for Wine / Hangover binaries
  RUN ln -s /opt/hangover/bin/wine /usr/local/bin/wine && \
      ln -s /opt/hangover/bin/wine64 /usr/local/bin/wine64 && \
      ln -s /opt/hangover/bin/winecfg /usr/local/bin/winecfg && \
      ln -s /opt/hangover/bin/wineserver /usr/local/bin/wineserver

  # Set environment variables
  ENV WINEPREFIX=/root/.wine
  ENV DISPLAY=:99
  ENV WINEDEBUG=-all

  # Pre-create Wine prefix, install WebView2 and MT5 setup headless
  RUN Xvfb :99 -screen 0 1024x768x16 & \
      export DISPLAY=:99 && \
      sleep 2 && \
      winecfg -v=win11 && \
      sleep 2 && \
      curl -L "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/f2910a1e-e5a6-4f17-b52d-7faf525d17f8/MicrosoftEdgeWebview2Setup.exe" -o webview2.exe && \
      wine webview2.exe /silent /install && \
      sleep 5 && \
      curl -L "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" -o mt5setup.exe && \
      wine mt5setup.exe /auto && \
      # Wait for MT5 terminal to be fully installed in portable directory
      while [ ! -f "/root/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe" ]; do sleep 1; done && \
      sleep 5 && \
      wineserver -k && \
      rm -f webview2.exe mt5setup.exe

  # Copy validation and entrypoint scripts
  COPY config-validator.sh /usr/local/bin/config-validator.sh
  COPY entrypoint.sh /entrypoint.sh
  RUN chmod +x /usr/local/bin/config-validator.sh /entrypoint.sh

  ENTRYPOINT ["/entrypoint.sh"]
  ```

- [ ] **Step 5: Verify scripts syntax**
  Check the bash script syntax using bash lint or verification commands.
  
  Run: `bash -n config-validator.sh entrypoint.sh`
  Expected: Return with exit code 0 (no syntax errors).

- [ ] **Step 6: Commit changes**
  
  ```bash
  git add Dockerfile .dockerignore config-validator.sh entrypoint.sh
  git commit -m "feat: Add Dockerfile and helper scripts for headless ARM64 MT5 container"
  ```

---

### Task 2: Orchestration Templates & Local Testing

**Files:**
- Create: `docker-compose.yml.template`
- Create: `mt5-instance@.service`

**Interfaces:**
- Consumes: Base Docker image built in Task 1.
- Produces: Systemd template and Docker Compose blueprint for execution.

- [ ] **Step 1: Create `docker-compose.yml.template`**
  Define a reference compose setup for local verification and quick-starts.
  
  ```yaml
  version: '3.8'

  services:
    mt5-instance:
      image: ghcr.io/dixit6054/mt5-hangover:arm64-v1.0
      container_name: mt5-instance-demo
      pid: "host"
      environment:
        - DISPLAY=:99
      volumes:
        - ./wine_prefix:/root/.wine
        - ./config:/etc/mt5/config
        - ./logs:/root/.wine/drive_c/Program Files/MetaTrader 5/logs
        - ./mql5_logs:/root/.wine/drive_c/Program Files/MetaTrader 5/MQL5/Logs
      restart: always
  ```

- [ ] **Step 2: Create `mt5-instance@.service`**
  Write the production systemd service template that targets Docker containers in host PID namespace.
  
  ```ini
  [Unit]
  Description=Docker MetaTrader 5 Instance - %i
  After=docker.service
  Requires=docker.service

  [Service]
  TimeoutStartSec=0
  Restart=always
  ExecStartPre=-/usr/bin/docker kill mt5-%i
  ExecStartPre=-/usr/bin/docker rm mt5-%i
  ExecStart=/usr/bin/docker run --name mt5-%i \
    --pid=host \
    -v /home/ubuntu/mt5_instances/%i/wine_prefix:/root/.wine \
    -v /home/ubuntu/mt5_instances/%i/config:/etc/mt5/config \
    -v /home/ubuntu/mt5_instances/%i/logs:/root/.wine/drive_c/Program\ Files/MetaTrader\ 5/logs \
    -v /home/ubuntu/mt5_instances/%i/mql5_logs:/root/.wine/drive_c/Program\ Files/MetaTrader\ 5/MQL5/Logs \
    -e DISPLAY=:99 \
    ghcr.io/dixit6054/mt5-hangover:arm64-v1.0
  ExecStop=/usr/bin/docker stop mt5-%i

  [Install]
  WantedBy=multi-user.target
  ```

- [ ] **Step 3: Commit files**
  
  ```bash
  git add docker-compose.yml.template mt5-instance@.service
  git commit -m "feat: Add docker-compose and systemd unit templates for orchestrating MT5 containers"
  ```

---

### Task 3: Refactor remote_deploy.py

**Files:**
- Modify: `mcp_server_code/src/mcp_mt5/remote_deploy.py`

**Interfaces:**
- Consumes: `deploy_remote_instance(...)` signature.
- Produces: Updated Docker-aware `deploy_remote_instance` implementation.

- [ ] **Step 1: Refactor `deploy_remote_instance`**
  Modify the implementation in `mcp_server_code/src/mcp_mt5/remote_deploy.py` to set up instance directories on the host, copy config files, pull the Docker image, and run the service via systemd-docker.

  Replace the execution part of `deploy_remote_instance` with the following:
  ```python
  # 1. Base SSH command
  key_opt = ["-i", key_file] if key_file else []
  ssh_base = ["ssh", "-o", "StrictHostKeyChecking=no"] + key_opt + [f"{user}@{host}"]
  scp_base = ["scp", "-o", "StrictHostKeyChecking=no"] + key_opt
  
  logs = []
  
  def run_ssh(cmd: str):
      logs.append(f"Running on remote: {cmd}")
      res = subprocess.run(ssh_base + [cmd], capture_output=True, text=True)
      if res.returncode != 0:
          raise RuntimeError(f"SSH command failed: {cmd}\nStderr: {res.stderr}")
      return res.stdout

  # 2. Setup Host Directory Structure
  host_instance_path = f"/home/{user}/mt5_instances/{instance_name}"
  host_config_path = f"{host_instance_path}/config"
  host_prefix_path = f"{host_instance_path}/wine_prefix"
  
  run_ssh(f"mkdir -p \"{host_config_path}\" \"{host_prefix_path}\"")
  
  # 3. If exists, copy legacy ~/.mt5 folder to seed wine_prefix
  run_ssh(f"if [ -d ~/.mt5 ] && [ ! -f \"{host_prefix_path}/system.reg\" ]; then cp -r ~/.mt5/* \"{host_prefix_path}/\"; echo 'Seeded Wine prefix'; fi")

  # 4. Copy EA and Preset if provided to host_config_path
  if ea_local_path and os.path.exists(ea_local_path):
      ea_name = Path(ea_local_path).name
      scp_cmd = scp_base + [ea_local_path, f"{user}@{host}:{host_config_path}/{ea_name}"]
      logs.append(f"SCPing EA: {' '.join(scp_cmd)}")
      subprocess.run(scp_cmd, check=True)
  
  if preset_local_path and os.path.exists(preset_local_path):
      preset_name = Path(preset_local_path).name
      scp_cmd = scp_base + [preset_local_path, f"{user}@{host}:{host_config_path}/{preset_name}"]
      logs.append(f"SCPing Preset: {' '.join(scp_cmd)}")
      subprocess.run(scp_cmd, check=True)

  # 5. Generate startup.ini inside host_config_path
  config_ini_lines = [
      "[Common]",
      f"Login={account_login}",
      f"Password={account_password}",
      f"Server={account_server}",
      "",
      "[Charts]",
      f"Symbol={symbol}",
      "",
      "[Experts]",
      "AllowDllImport=1",
      "Enabled=1"
  ]
  
  if ea_local_path:
      ea_name = Path(ea_local_path).name
      config_ini_lines.append(f"Expert=Experts\\{ea_name}")
      config_ini_lines.append(f"Symbol={symbol}")
      config_ini_lines.append("Period=H1")
      
      if preset_local_path:
          preset_name = Path(preset_local_path).name
          config_ini_lines.append(f"ExpertParameters=Presets\\{preset_name}")
          
  config_ini = "\n".join(config_ini_lines) + "\n"
  
  with tempfile.NamedTemporaryFile("w", delete=False, suffix=".ini") as f:
      f.write(config_ini)
      local_ini = f.name
      
  scp_cmd = scp_base + [local_ini, f"{user}@{host}:{host_config_path}/startup.ini"]
  logs.append("SCPing startup.ini")
  subprocess.run(scp_cmd, check=True)
  os.unlink(local_ini)

  # 6. Docker pull on remote
  docker_image = "ghcr.io/dixit6054/mt5-hangover:arm64-v1.0"
  logs.append("Pulling Docker image on remote host")
  run_ssh(f"sudo docker pull {docker_image}")

  # 7. Setup systemd service
  service_name = f"mt5_{instance_name.replace('.', '').replace('/', '')}"
  service_content = textwrap.dedent(f"""\
  [Unit]
  Description=Dockerized MT5 Instance {instance_name}
  After=docker.service
  Requires=docker.service

  [Service]
  TimeoutStartSec=0
  Restart=always
  ExecStartPre=-/usr/bin/docker kill {service_name}
  ExecStartPre=-/usr/bin/docker rm {service_name}
  ExecStart=/usr/bin/docker run --name {service_name} \\
    --pid=host \\
    -v {host_prefix_path}:/root/.wine \\
    -v {host_config_path}:/etc/mt5/config \\
    -v {host_instance_path}/logs:/root/.wine/drive_c/Program\\ Files/MetaTrader\\ 5/logs \\
    -v {host_instance_path}/mql5_logs:/root/.wine/drive_c/Program\\ Files/MetaTrader\\ 5/MQL5/Logs \\
    -e DISPLAY=:99 \\
    {docker_image}
  ExecStop=/usr/bin/docker stop {service_name}

  [Install]
  WantedBy=multi-user.target
  """)
  
  with tempfile.NamedTemporaryFile("w", delete=False, suffix=".service") as f:
      f.write(service_content)
      local_service = f.name
      
  scp_cmd = scp_base + [local_service, f"{user}@{host}:/tmp/{service_name}.service"]
  subprocess.run(scp_cmd, check=True)
  os.unlink(local_service)
  
  run_ssh(f"sudo mv /tmp/{service_name}.service /etc/systemd/system/")
  run_ssh("sudo systemctl daemon-reload")
  run_ssh(f"sudo systemctl enable {service_name}")
  run_ssh(f"sudo systemctl restart {service_name}")
  
  logs.append(f"Dockerized service {service_name} started.")
  
  return {
      "status": "success",
      "instance_name": instance_name,
      "service_name": service_name,
      "logs": logs
  }
  ```

- [ ] **Step 2: Commit remote_deploy.py refactor**
  
  ```bash
  git add mcp_server_code/src/mcp_mt5/remote_deploy.py
  git commit -m "refactor: Update remote_deploy.py to deploy MT5 via Docker and systemd"
  ```

---

### Task 4: Documentation & Integration Script

**Files:**
- Create: `docs/docker_deployment.md`
- Modify: `README.md`
- Create: `tests/test_docker_config_validation.sh`

**Interfaces:**
- Consumes: Completed Docker files and scripts.
- Produces: Integration tests for validation, updated end-user manuals.

- [ ] **Step 1: Create `docs/docker_deployment.md`**
  Document the design, directory structures, how to build/run the image, and troubleshooting tips.
  
  ```markdown
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
    -e DISPLAY=:99 \
    ghcr.io/dixit6054/mt5-hangover:arm64-v1.0
  ```
  ```

- [ ] **Step 2: Update `README.md`**
  Add a section detailing the new Docker Quick Start and ARM64/Hangover specifics.

- [ ] **Step 3: Create `tests/test_docker_config_validation.sh`**
  Create an integration test script that verifies the `config-validator.sh` script rejects bad configurations and accepts correct configurations.
  
  ```bash
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
  
  rm -rf "${TEMP_CONFIG}" temp_val.sh
  echo "All integration tests for validator passed!"
  ```

- [ ] **Step 4: Execute integration test script**
  Run: `bash tests/test_docker_config_validation.sh`
  Expected: Output `All integration tests for validator passed!`

- [ ] **Step 5: Commit changes**
  
  ```bash
  git add docs/docker_deployment.md README.md tests/test_docker_config_validation.sh
  git commit -m "docs: Add Docker deployment guide and config validation test"
  ```
