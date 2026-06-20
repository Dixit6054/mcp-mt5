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
