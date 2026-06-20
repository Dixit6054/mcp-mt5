# MT5 Dockerization, VPS Cleanup, and Coolify Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up the Oracle ARM64 VPS, migrate both host-level/legacy MT5 terminals into Docker containers managed by Coolify, and verify successful login using secure VNC port forwarding.

**Architecture:** Build the generic base image with `x11vnc` and runtime auto-installation on the VPS, seed container volume prefix folders from legacy host-level prefix directories to carry over existing login states, and deploy both instances under a unified Coolify Docker Compose project.

**Tech Stack:** Ubuntu 24.04 ARM64, Hangover (Wine 11.9), Docker, Coolify, VNC (x11vnc), Bash, SSH/SCP.

## Global Constraints
- **Production-only footprint**: No Python, development dependencies, or MCP servers inside the Docker image.
- **Port Security**: Expose VNC ports (`5900` inside container) ONLY to the host's localhost loopback interface (`127.0.0.1:5901` and `127.0.0.1:5902`) to prevent public internet exposure.
- **Runtime Installation**: Emulation-heavy Wine setup tasks (WebView2 and MT5 installation) are performed at runtime (first boot) inside the container rather than at build time.

---

### Task 10: Oracle VPS Cleanup

**Files:**
- Modify: Remote VPS Host directories (`/home/ubuntu`)

**Interfaces:**
- Consumes: None
- Produces: None

- [ ] **Step 1: Execute directory removal commands on remote VPS**
  Run:
  ```bash
  ssh -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" -o StrictHostKeyChecking=no ubuntu@147.224.213.171 "rm -rf ~/hangover ~/hangover-pkg ~/mt5 '~'"
  ```

- [ ] **Step 2: Clean up unused docker caches on remote VPS**
  Run:
  ```bash
  ssh -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" -o StrictHostKeyChecking=no ubuntu@147.224.213.171 "sudo docker system prune -a -f --volumes"
  ```

---

### Task 11: Seeding and Configuration Migration

**Files:**
- Modify: `/home/ubuntu/mt5_instances`
- Modify: `/home/ubuntu/.mt5` (copy target)

**Interfaces:**
- Consumes: Legacy prefix configs in `/home/ubuntu/.mt5`
- Produces: Seeded prefix volumes and config files under `/home/ubuntu/mt5_instances`

- [ ] **Step 1: Kill active Wine processes**
  Run:
  ```bash
  ssh -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" -o StrictHostKeyChecking=no ubuntu@147.224.213.171 "killall -9 Wineserver terminal64.exe winedevice.exe || true"
  ```

- [ ] **Step 2: Stop systemd service**
  Run:
  ```bash
  ssh -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" -o StrictHostKeyChecking=no ubuntu@147.224.213.171 "sudo systemctl stop mt5_mt5_second_account && sudo systemctl disable mt5_mt5_second_account && sudo rm -f /etc/systemd/system/mt5_mt5_second_account.service && sudo systemctl daemon-reload"
  ```

- [ ] **Step 3: Create container instances mount dirs**
  Run:
  ```bash
  ssh -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" -o StrictHostKeyChecking=no ubuntu@147.224.213.171 "mkdir -p ~/mt5_instances/mt5_first_account/config ~/mt5_instances/mt5_first_account/wine_prefix ~/mt5_instances/mt5_second_account/config"
  ```

- [ ] **Step 4: Seed primary account prefix**
  Run:
  ```bash
  ssh -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" -o StrictHostKeyChecking=no ubuntu@147.224.213.171 "cp -r ~/.mt5/* ~/mt5_instances/mt5_first_account/wine_prefix/"
  ```

- [ ] **Step 5: Write primary config**
  Create local temporary file `startup_first.ini`:
  ```ini
  [Common]
  Login=108605529
  Server=MetaQuotes-Demo
  
  [Charts]
  Symbol=EURUSD
  
  [Experts]
  AllowDllImport=1
  Enabled=1
  ```
  SCP to VPS:
  ```bash
  scp -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" startup_first.ini ubuntu@147.224.213.171:/home/ubuntu/mt5_instances/mt5_first_account/config/startup.ini
  ```

- [ ] **Step 6: Write secondary config**
  Create local temporary file `startup_second.ini`:
  ```ini
  [Common]
  Login=5052017130
  Password=GjOnAg@7
  Server=MetaQuotes-Demo
  
  [Charts]
  Symbol=EURUSD
  
  [Experts]
  AllowDllImport=1
  Enabled=1
  ```
  SCP to VPS:
  ```bash
  scp -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" startup_second.ini ubuntu@147.224.213.171:/home/ubuntu/mt5_instances/mt5_second_account/config/startup.ini
  ```

---

### Task 12: Build & Deploy via Coolify

**Files:**
- Create: `docker-compose.yml`
- Modify: `Dockerfile`, `entrypoint.sh`, `config-validator.sh` (build step)

**Interfaces:**
- Consumes: Seeded configuration folders and the generic Dockerfile
- Produces: Docker image `mt5-hangover:latest` and Coolify deployment configuration

- [ ] **Step 1: Upload build files to VPS**
  Run:
  ```bash
  ssh -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" -o StrictHostKeyChecking=no ubuntu@147.224.213.171 "mkdir -p ~/mt5_instances/build"
  scp -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" Dockerfile entrypoint.sh config-validator.sh ubuntu@147.224.213.171:/home/ubuntu/mt5_instances/build/
  ```

- [ ] **Step 2: Run Docker Build on VPS**
  Run:
  ```bash
  ssh -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" -o StrictHostKeyChecking=no ubuntu@147.224.213.171 "sudo docker build -t mt5-hangover:latest ~/mt5_instances/build"
  ```

- [ ] **Step 3: Write Compose file**
  Create local temporary file `docker-compose.yml`:
  ```yaml
  version: '3.8'
  services:
    mt5-primary:
      image: mt5-hangover:latest
      container_name: mt5-primary
      pid: host
      ports:
        - "127.0.0.1:5901:5900"
      volumes:
        - /home/ubuntu/mt5_instances/mt5_first_account/wine_prefix:/root/.wine
        - /home/ubuntu/mt5_instances/mt5_first_account/config:/etc/mt5/config
      environment:
        - DISPLAY=:99
      restart: always

    mt5-secondary:
      image: mt5-hangover:latest
      container_name: mt5-secondary
      pid: host
      ports:
        - "127.0.0.1:5902:5900"
      volumes:
        - /home/ubuntu/mt5_instances/mt5_second_account/wine_prefix:/root/.wine
        - /home/ubuntu/mt5_instances/mt5_second_account/config:/etc/mt5/config
      environment:
        - DISPLAY=:99
      restart: always
  ```
  SCP to VPS:
  ```bash
  scp -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" docker-compose.yml ubuntu@147.224.213.171:/home/ubuntu/mt5_instances/docker-compose.yml
  ```

- [ ] **Step 4: Create Coolify deployment**
  1. Open the Coolify dashboard at `http://147.224.213.171:8000`.
  2. Create a new **Project** named `MT5-Production` (if not already existing).
  3. Inside the environment, click **New Resource** -> select **Docker Compose**.
  4. Paste the content of `/home/ubuntu/mt5_instances/docker-compose.yml` into the text area.
  5. Select **Raw Compose** and configure the container profiles.
  6. Click **Deploy**.

---

### Task 13: Secure VNC Verification & Walkthrough

**Files:**
- None

**Interfaces:**
- Consumes: Running Coolify container instances on ports 5901 and 5902
- Produces: Visual connection confirmation

- [ ] **Step 1: Establish VNC SSH Tunnels**
  Run local port forwarding:
  ```bash
  ssh -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" -L 5901:127.0.0.1:5901 -L 5902:127.0.0.1:5902 ubuntu@147.224.213.171
  ```

- [ ] **Step 2: Verify mt5-primary**
  - Connect VNC client to `localhost:5901`.
  - Confirm MT5 UI loads and is logged in.

- [ ] **Step 3: Verify mt5-secondary**
  - Connect VNC client to `localhost:5902`.
  - Confirm MT5 UI loads and is logged in.

- [ ] **Step 4: Purge legacy files**
  Delete legacy folders:
  ```bash
  ssh -i "C:\Users\dixit\Desktop\mt5 antigravity\ssh-key-2026-06-19 (1).key" ubuntu@147.224.213.171 "rm -rf ~/.mt5 ~/.mt5_second_account"
  ```
