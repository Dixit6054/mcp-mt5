import os
import subprocess
import tempfile
import textwrap
import base64
import json
from pathlib import Path
from typing import Optional

def deploy_remote_instance(
    host: str,
    user: str,
    key_file: str,
    instance_name: str,
    account_login: int,
    account_password: str,
    account_server: str,
    symbol: str = "EURUSD",
    ea_local_path: Optional[str] = None,
    preset_local_path: Optional[str] = None,
) -> dict:
    """Deploy a new MT5 instance on a remote Linux VPS via SSH and SCP."""
    
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
    host_instance_path = f"/home/{user}/mt5_instances/{instance_name.lstrip('~/.')}"
    host_config_path = f"{host_instance_path}/config"
    host_prefix_path = f"{host_instance_path}/wine_prefix"
    
    print(f"[*] Setting up remote directory structure at {host_instance_path}...", flush=True)
    run_ssh(f"mkdir -p \"{host_config_path}\" \"{host_prefix_path}\"")
    
    # 3. If exists, copy legacy ~/.mt5 folder to seed wine_prefix
    print("[*] Seeding Wine prefix from legacy ~/.mt5 folder if present...", flush=True)
    run_ssh(f"if [ -d ~/.mt5 ] && [ ! -f \"{host_prefix_path}/system.reg\" ]; then cp -r ~/.mt5/* \"{host_prefix_path}/\"; echo 'Seeded Wine prefix'; fi")

    # 4. Copy EA and Preset if provided to host_config_path
    if ea_local_path and os.path.exists(ea_local_path):
        ea_name = Path(ea_local_path).name
        print(f"[*] SCP-ing EA binary {ea_name} to remote VPS config directory...", flush=True)
        scp_cmd = scp_base + [ea_local_path, f"{user}@{host}:{host_config_path}/{ea_name}"]
        logs.append(f"SCPing EA: {' '.join(scp_cmd)}")
        subprocess.run(scp_cmd, check=True)
    
    if preset_local_path and os.path.exists(preset_local_path):
        preset_name = Path(preset_local_path).name
        print(f"[*] SCP-ing Preset file {preset_name} to remote VPS config directory...", flush=True)
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
    
    print("[*] Generating and copying startup.ini...", flush=True)
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".ini") as f:
        f.write(config_ini)
        local_ini = f.name
        
    scp_cmd = scp_base + [local_ini, f"{user}@{host}:{host_config_path}/startup.ini"]
    logs.append("SCPing startup.ini")
    subprocess.run(scp_cmd, check=True)
    os.unlink(local_ini)

    # 6. Docker image setup (build locally if not exists)
    docker_image = "ghcr.io/dixit6054/mt5-hangover:arm64-v1.0"
    
    current_file = Path(__file__).resolve()
    workspace_root = None
    for parent in current_file.parents:
        if (parent / "Dockerfile").exists():
            workspace_root = parent
            break
            
    if workspace_root:
        host_build_path = f"{host_instance_path}/build"
        run_ssh(f"mkdir -p \"{host_build_path}\"")
        
        print("[*] SCP-ing Dockerfile, entrypoint, and validator to remote VPS...", flush=True)
        for f_name in ["Dockerfile", "entrypoint.sh", "config-validator.sh"]:
            local_f = workspace_root / f_name
            if local_f.exists():
                scp_cmd = scp_base + [str(local_f), f"{user}@{host}:{host_build_path}/{f_name}"]
                logs.append(f"SCPing {f_name} to build folder")
                subprocess.run(scp_cmd, check=True)
                
        print(f"[*] Checking if Docker image {docker_image} exists on remote VPS...", flush=True)
        image_check = run_ssh(f"sudo docker images -q {docker_image} 2>/dev/null || true").strip()
        if not image_check:
            print(f"[!] Docker image not found on VPS. Starting native remote build of {docker_image}...", flush=True)
            print("[!] Note: This is a fast build that only sets up the runtime and x11vnc. It takes approximately 15-30 seconds. Please wait...", flush=True)
            run_ssh(f"sudo docker build -t {docker_image} \"{host_build_path}\"")
            print("[*] Docker build completed successfully!", flush=True)
        else:
            print(f"[*] Docker image {docker_image} already exists on VPS. Skipping build.", flush=True)
    else:
        print("[!] Workspace root not resolved. Attempting docker pull fallback...", flush=True)
        run_ssh(f"sudo docker pull {docker_image}")

    # 7. Setup systemd service
    service_name = f"mt5_{instance_name.replace('.', '').replace('/', '').replace('~', '')}"
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
      -p 127.0.0.1:5900:5900 \\
      -v {host_prefix_path}:/root/.wine \\
      -v {host_config_path}:/etc/mt5/config \\
      -e DISPLAY=:99 \\
      {docker_image}
    ExecStop=/usr/bin/docker stop {service_name}
 
    [Install]
    WantedBy=multi-user.target
    """)
    
    print(f"[*] Writing and deploying systemd service {service_name}...", flush=True)
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
    
    print(f"[*] Dockerized service {service_name} successfully started and enabled!", flush=True)
    logs.append(f"Dockerized service {service_name} started.")
    
    return {
        "status": "success",
        "instance_name": instance_name,
        "service_name": service_name,
        "logs": logs
    }


def deploy_coolify_instance(
    host: str,
    user: str,
    key_file: str,
    instance_name: str,
    account_login: int,
    account_password: str,
    account_server: str,
    symbol: str = "EURUSD",
    ea_local_path: Optional[str] = None,
    preset_local_path: Optional[str] = None,
    vnc_port: Optional[int] = None,
    coolify_token: str = "XuYhKAKiiErqwsWgdmY1PcLiMndU6Ez8WvzXhSZQ",
    coolify_service_uuid: str = "nipi1hhqa5cb2qdyoptrik5p",
) -> dict:
    """Deploy a new MT5 instance on a remote Linux VPS via Coolify orchestration."""
    
    # 1. Base SSH/SCP commands
    key_opt = ["-i", key_file] if key_file else []
    ssh_base = ["ssh", "-o", "StrictHostKeyChecking=no"] + key_opt + [f"{user}@{host}"]
    scp_base = ["scp", "-o", "StrictHostKeyChecking=no"] + key_opt
    
    logs = []
    
    def run_ssh(cmd: str) -> str:
        logs.append(f"Running on remote: {cmd}")
        res = subprocess.run(ssh_base + [cmd], capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"SSH command failed: {cmd}\nStderr: {res.stderr}")
        return res.stdout

    # 2. Setup Host Directory Structure (using /home/{user}/boot/ for configuration)
    host_boot_path = f"/home/{user}/boot/{instance_name.lstrip('~/.')}"
    host_instance_path = f"/home/{user}/mt5_instances/{instance_name.lstrip('~/.')}"
    host_prefix_path = f"{host_instance_path}/wine_prefix"
    
    logs.append(f"Setting up remote directory structure at {host_boot_path} and {host_prefix_path}...")
    run_ssh(f"mkdir -p \"{host_boot_path}\" \"{host_prefix_path}\"")
    
    # 3. Seeding Wine prefix from legacy ~/.mt5 folder if present
    run_ssh(f"if [ -d ~/.mt5 ] && [ ! -f \"{host_prefix_path}/system.reg\" ]; then cp -r ~/.mt5/* \"{host_prefix_path}/\"; echo 'Seeded Wine prefix'; fi")

    # 4. Copy EA and Preset if provided to host_boot_path
    if ea_local_path and os.path.exists(ea_local_path):
        ea_name = Path(ea_local_path).name
        logs.append(f"SCPing EA binary {ea_name} to boot directory...")
        scp_cmd = scp_base + [ea_local_path, f"{user}@{host}:{host_boot_path}/{ea_name}"]
        subprocess.run(scp_cmd, check=True)
    
    if preset_local_path and os.path.exists(preset_local_path):
        preset_name = Path(preset_local_path).name
        logs.append(f"SCPing Preset file {preset_name} to boot directory...")
        scp_cmd = scp_base + [preset_local_path, f"{user}@{host}:{host_boot_path}/{preset_name}"]
        subprocess.run(scp_cmd, check=True)

    # 5. Generate startup.ini inside host_boot_path
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
    
    logs.append("Generating and copying startup.ini...")
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".ini") as f:
        f.write(config_ini)
        local_ini = f.name
        
    scp_cmd = scp_base + [local_ini, f"{user}@{host}:{host_boot_path}/startup.ini"]
    subprocess.run(scp_cmd, check=True)
    os.unlink(local_ini)

    # 6. Retrieve current docker-compose from Coolify
    logs.append("Fetching current docker-compose config from Coolify...")
    curl_get_cmd = f"curl -s -H 'Authorization: Bearer {coolify_token}' http://localhost:8000/api/v1/services/{coolify_service_uuid}"
    service_json_str = run_ssh(curl_get_cmd)
    try:
        service_data = json.loads(service_json_str)
    except Exception as e:
        raise RuntimeError(f"Failed to parse service JSON from Coolify: {e}\nResponse: {service_json_str}")
        
    docker_compose_raw = service_data.get("docker_compose_raw", "")
    if not docker_compose_raw:
        raise RuntimeError("Service JSON from Coolify did not contain docker_compose_raw field.")
        
    # Check if the returned string is plain text or base64
    if "\n" in docker_compose_raw or " " in docker_compose_raw:
        compose_content = docker_compose_raw
    else:
        try:
            compose_content = base64.b64decode(docker_compose_raw).decode("utf-8")
        except Exception:
            compose_content = docker_compose_raw
            
    compose_lines = compose_content.splitlines()

    # 7. Auto-discover next VNC port if not specified
    if vnc_port is None:
        used_ports = []
        for line in compose_lines:
            if "5900" in line:
                import re
                port_match = re.search(r'(\d+):5900', line)
                if port_match:
                    used_ports.append(int(port_match.group(1)))
        
        vnc_port = max(used_ports) + 1 if used_ports else 5901
        logs.append(f"Auto-assigned VNC port {vnc_port} (used ports: {used_ports})")

    # 8. Modify/Append service block in compose file
    service_name = f"mt5-{instance_name}"
    
    # Remove existing service of the same name if exists
    clean_lines = []
    skipping = False
    for line in compose_lines:
        if line.startswith(f"  {service_name}:"):
            skipping = True
            continue
        if skipping:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if line.strip() and not line.strip().startswith("#") and indent <= 2:
                skipping = False
        if not skipping:
            clean_lines.append(line)

    # Reconstruct docker compose text
    new_compose_lines = []
    services_idx = -1
    
    for i, line in enumerate(clean_lines):
        new_compose_lines.append(line)
        if line.strip() == "services:":
            services_idx = len(new_compose_lines) - 1

    new_service_block = (
        f"  {service_name}:\n"
        f"    image: mt5-hangover:latest\n"
        f"    container_name: {service_name}\n"
        f"    pid: host\n"
        f"    ports:\n"
        f"      - \"127.0.0.1:{vnc_port}:5900\"\n"
        f"    volumes:\n"
        f"      - {host_prefix_path}:/root/.wine\n"
        f"      - {host_boot_path}:/etc/mt5/config\n"
        f"    environment:\n"
        f"      - DISPLAY=:99\n"
        f"    restart: always"
    )
    
    if services_idx != -1:
        new_compose_lines.insert(services_idx + 1, new_service_block.rstrip())
    else:
        new_compose_lines.append("services:")
        new_compose_lines.append(new_service_block.rstrip())

    final_compose = "\n".join(new_compose_lines) + "\n"

    # 9. Update Coolify Service Compose config
    logs.append("Uploading updated docker-compose config to Coolify...")
    final_compose_b64 = base64.b64encode(final_compose.encode("utf-8")).decode("utf-8")
    
    patch_payload = json.dumps({"docker_compose_raw": final_compose_b64})
    run_ssh(f"echo '{patch_payload}' > /tmp/coolify_patch_payload.json")
    
    curl_patch_cmd = (
        f"curl -s -X PATCH -H 'Authorization: Bearer {coolify_token}' "
        f"-H 'Content-Type: application/json' "
        f"-d @/tmp/coolify_patch_payload.json "
        f"http://localhost:8000/api/v1/services/{coolify_service_uuid}"
    )
    patch_response = run_ssh(curl_patch_cmd)
    run_ssh("rm -f /tmp/coolify_patch_payload.json")
    
    logs.append(f"Patch response: {patch_response}")

    # 10. Restart/Redeploy Coolify Service
    logs.append("Triggering service restart/redeploy in Coolify...")
    curl_restart_cmd = (
        f"curl -s -H 'Authorization: Bearer {coolify_token}' "
        f"http://localhost:8000/api/v1/services/{coolify_service_uuid}/restart"
    )
    restart_response = run_ssh(curl_restart_cmd)
    logs.append(f"Restart response: {restart_response}")

    return {
        "status": "success",
        "instance_name": instance_name,
        "service_name": service_name,
        "vnc_port": vnc_port,
        "logs": logs
    }


