import os
import subprocess
import tempfile
import textwrap
import base64
import json
from pathlib import Path
from typing import Optional

def deploy_to_production(
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
    webrequest_urls: Optional[str] = None,
    coolify_token: str = "XuYhKAKiiErqwsWgdmY1PcLiMndU6Ez8WvzXhSZQ",
    coolify_service_uuid: str = "nipi1hhqa5cb2qdyoptrik5p",
) -> dict:
    """Deploy a new MT5 instance on a remote Linux VPS via Coolify orchestration.

    PREREQUISITES:
    1. A target Linux VPS (ARM64) with Docker installed.
    2. Coolify running on the VPS (typically on port 8000).
    3. An existing MetaTrader 5 service created in Coolify (providing the coolify_service_uuid).
    4. Coolify API Token created in Coolify settings.
    5. SSH access configured on the VPS (user + private key) to upload configuration files.

    PARAMETERS:
    - host: The IP address or hostname of the remote Linux VPS.
    - user: The SSH username for connection (e.g. 'ubuntu', 'root').
    - key_file: Path to the local SSH private key file.
    - instance_name: Unique name for this terminal instance (e.g., 'primary', 'secondary').
    - account_login: MetaTrader 5 trading account login number.
    - account_password: MetaTrader 5 trading account password.
    - account_server: Broker server name (e.g., 'MetaQuotes-Demo').
    - symbol: Chart symbol to open on startup (e.g., 'EURUSD', 'XAUUSD'). Defaults to 'EURUSD'.
    - ea_local_path: Optional path to local compiled EA binary (.ex5) to upload.
    - preset_local_path: Optional path to local EA settings file (.set) to upload.
    - vnc_port: Optional specific port mapping for VNC. If omitted, the tool auto-detects and increments (e.g., 5901, 5902).
    - webrequest_urls: Optional semicolon-separated list of URLs to whitelist for EA WebRequests (e.g. 'https://api.mybroker.com;https://webhook.site').
    - coolify_token: Coolify API Token. Defaults to the preset production token.
    - coolify_service_uuid: UUID of the Coolify service stack to append the instance to.
    """
    
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

    env_block = [f"      - DISPLAY=:99"]
    if webrequest_urls:
        env_block.append(f"      - WEBREQUEST_URLS={webrequest_urls}")
    env_str = "\n".join(env_block)

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
        f"{env_str}\n"
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


