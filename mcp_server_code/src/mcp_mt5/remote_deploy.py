import os
import subprocess
import tempfile
import textwrap
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
        
        for f_name in ["Dockerfile", "entrypoint.sh", "config-validator.sh"]:
            local_f = workspace_root / f_name
            if local_f.exists():
                scp_cmd = scp_base + [str(local_f), f"{user}@{host}:{host_build_path}/{f_name}"]
                logs.append(f"SCPing {f_name} to build folder")
                subprocess.run(scp_cmd, check=True)
                
        image_check = run_ssh(f"sudo docker images -q {docker_image} 2>/dev/null || true").strip()
        if not image_check:
            logs.append(f"Docker image {docker_image} not found on VPS. Building natively on remote host (this will take several minutes)...")
            run_ssh(f"sudo docker build -t {docker_image} \"{host_build_path}\"")
        else:
            logs.append(f"Docker image {docker_image} already exists on VPS. Skipping build.")
    else:
        logs.append("Workspace root not resolved. Attempting docker pull fallback...")
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

