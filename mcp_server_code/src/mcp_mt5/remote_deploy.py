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

    # 2. Clone Base Prefix
    target_prefix = f"~/{instance_name}"
    run_ssh(f"if [ ! -d {target_prefix} ]; then cp -r ~/.mt5 {target_prefix}; echo 'Cloned base prefix'; else echo 'Prefix already exists'; fi")
    
    # Clean up default charts so only the designated chart opens
    run_ssh(f"rm -f \"{target_prefix}/drive_c/Program Files/MetaTrader 5/Profiles/Charts/Default/\"*.chr")
    
    # 3. Copy EA and Preset if provided
    base_mt5_dir = f"{target_prefix}/drive_c/Program Files/MetaTrader 5"
    run_ssh(f"mkdir -p \"{base_mt5_dir}/MQL5/Experts\" \"{base_mt5_dir}/MQL5/Presets\"")
    if ea_local_path and os.path.exists(ea_local_path):
        ea_name = Path(ea_local_path).name
        scp_cmd = scp_base + [ea_local_path, f"{user}@{host}:{target_prefix}/drive_c/Program Files/MetaTrader 5/MQL5/Experts/{ea_name}"]
        logs.append(f"SCPing EA: {' '.join(scp_cmd)}")
        subprocess.run(scp_cmd, check=True)
    
    if preset_local_path and os.path.exists(preset_local_path):
        preset_name = Path(preset_local_path).name
        scp_cmd = scp_base + [preset_local_path, f"{user}@{host}:{target_prefix}/drive_c/Program Files/MetaTrader 5/MQL5/Presets/{preset_name}"]
        logs.append(f"SCPing Preset: {' '.join(scp_cmd)}")
        subprocess.run(scp_cmd, check=True)

    # 4. Generate startup config.ini
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
        
    scp_cmd = scp_base + [local_ini, f"{user}@{host}:{target_prefix}/drive_c/startup.ini"]
    logs.append(f"SCPing startup.ini")
    subprocess.run(scp_cmd, check=True)
    os.unlink(local_ini)

    # 5. Setup systemd service
    service_name = f"mt5_{instance_name.replace('.', '').replace('/', '')}"
    service_content = textwrap.dedent(f"""\
    [Unit]
    Description=MT5 Instance {instance_name}
    After=network.target

    [Service]
    Type=simple
    User={user}
    Environment="WINEPREFIX=/home/{user}/{instance_name.lstrip('~/')}"
    Environment="WINEDLLOVERRIDES=mscoree,mshtml="
    ExecStart=/usr/bin/xvfb-run -a /usr/bin/wine "C:/Program Files/MetaTrader 5/terminal64.exe" "/config:C:\\\\startup.ini"
    Restart=always

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
    
    logs.append(f"Service {service_name} started.")
    
    return {
        "status": "success",
        "instance_name": instance_name,
        "service_name": service_name,
        "logs": logs
    }
