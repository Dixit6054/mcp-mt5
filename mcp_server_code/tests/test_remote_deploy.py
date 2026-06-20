import os
import subprocess
from unittest.mock import MagicMock, patch
from pathlib import Path
from mcp_mt5.remote_deploy import deploy_remote_instance


@patch("mcp_mt5.remote_deploy.os.unlink")
@patch("mcp_mt5.remote_deploy.subprocess.run")
@patch("mcp_mt5.remote_deploy.tempfile.NamedTemporaryFile")
def test_deploy_remote_instance(mock_tempfile, mock_run, mock_unlink, tmp_path):
    # Setup mock tempfiles
    mock_file = MagicMock()
    mock_file.name = "mock_file.service"
    mock_tempfile.return_value.__enter__.return_value = mock_file
    
    # Mock subprocess.run returns dynamically based on command
    def run_side_effect(cmd_args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        cmd_str = " ".join(cmd_args)
        if "docker images -q" in cmd_str:
            res.stdout = ""  # Simulate image not existing
        else:
            res.stdout = "mock_ok"
        return res
    mock_run.side_effect = run_side_effect

    # Create dummy local files
    ea_file = tmp_path / "MyEA.ex5"
    ea_file.touch()
    preset_file = tmp_path / "MyEA.set"
    preset_file.touch()

    # Call deploy_remote_instance
    result = deploy_remote_instance(
        host="127.0.0.1",
        user="testuser",
        key_file="test.key",
        instance_name="test_instance",
        account_login=123456,
        account_password="password",
        account_server="BrokerServer",
        symbol="EURUSD",
        ea_local_path=str(ea_file),
        preset_local_path=str(preset_file),
    )

    # Verify status
    assert result["status"] == "success"
    assert result["instance_name"] == "test_instance"
    assert result["service_name"] == "mt5_test_instance"

    # Check that subprocess.run was called for SSH/SCP operations
    assert mock_run.call_count > 0
    calls = [call[0][0] for call in mock_run.call_args_list]
    print("CALLS IN TEST:", calls)

    # Verify that docker build was executed on remote
    assert any("docker build -t ghcr.io/dixit6054/mt5-hangover" in " ".join(c) for c in calls if isinstance(c, list))

    # Verify systemd service daemon-reload and restart was run
    assert any("systemctl daemon-reload" in " ".join(c) for c in calls if isinstance(c, list))
    assert any("systemctl restart mt5_test_instance" in " ".join(c) for c in calls if isinstance(c, list))


@patch("mcp_mt5.remote_deploy.os.unlink")
@patch("mcp_mt5.remote_deploy.subprocess.run")
@patch("mcp_mt5.remote_deploy.tempfile.NamedTemporaryFile")
def test_deploy_coolify_instance(mock_tempfile, mock_run, mock_unlink, tmp_path):
    import json
    import base64
    import textwrap

    # Setup mock tempfiles
    mock_file = MagicMock()
    mock_file.name = "mock_file.ini"
    mock_tempfile.return_value.__enter__.return_value = mock_file
    
    # Mock subprocess.run returns dynamically based on command
    def run_side_effect(cmd_args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        cmd_str = " ".join(cmd_args)
        if "curl -s" in cmd_str and "services" in cmd_str and "restart" not in cmd_str:
            # Return mock Coolify service JSON
            mock_yaml = textwrap.dedent("""\
            version: '3.8'
            services:
              mt5-primary:
                image: mt5-hangover:latest
                ports:
                  - "127.0.0.1:5901:5900"
            """)
            mock_b64 = base64.b64encode(mock_yaml.encode()).decode()
            res.stdout = json.dumps({"docker_compose_raw": mock_b64})
        else:
            res.stdout = "mock_ok"
        return res
    mock_run.side_effect = run_side_effect

    # Create dummy local files
    ea_file = tmp_path / "MyEA.ex5"
    ea_file.touch()

    # Call deploy_coolify_instance
    from mcp_mt5.remote_deploy import deploy_coolify_instance
    result = deploy_coolify_instance(
        host="127.0.0.1",
        user="testuser",
        key_file="test.key",
        instance_name="secondary",
        account_login=123456,
        account_password="password",
        account_server="BrokerServer",
        symbol="EURUSD",
        ea_local_path=str(ea_file),
    )

    # Verify status
    assert result["status"] == "success"
    assert result["instance_name"] == "secondary"
    assert result["service_name"] == "mt5-secondary"
    assert result["vnc_port"] == 5902

    # Check that subprocess.run was called for SSH/SCP operations
    assert mock_run.call_count > 0

