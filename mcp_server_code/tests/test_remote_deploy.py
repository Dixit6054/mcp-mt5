import os
import subprocess
from unittest.mock import MagicMock, patch
from pathlib import Path
from mcp_mt5.remote_deploy import deploy_to_production


@patch("mcp_mt5.remote_deploy.os.unlink")
@patch("mcp_mt5.remote_deploy.subprocess.run")
@patch("mcp_mt5.remote_deploy.tempfile.NamedTemporaryFile")
def test_deploy_to_production(mock_tempfile, mock_run, mock_unlink, tmp_path):
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

    # Call deploy_to_production
    result = deploy_to_production(
        host="127.0.0.1",
        user="testuser",
        key_file="test.key",
        instance_name="secondary",
        account_login=123456,
        account_password="password",
        account_server="BrokerServer",
        symbol="EURUSD",
        ea_local_path=str(ea_file),
        webrequest_urls="https://api.mybroker.com",
    )

    # Verify status
    assert result["status"] == "success"
    assert result["instance_name"] == "secondary"
    assert result["service_name"] == "mt5-secondary"
    assert result["vnc_port"] == 5902

    # Check that subprocess.run was called for SSH/SCP operations
    assert mock_run.call_count > 0

