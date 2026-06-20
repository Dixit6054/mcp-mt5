import subprocess
import sys


def install_coolify(host, user, key_file):
    key_opt = ["-i", key_file] if key_file else []
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no"] + key_opt + [f"{user}@{host}"]

    # Official Coolify one-liner installation script
    install_cmd = "curl -fsSL https://cdn.coollabs.io/coolify/install.sh | sudo bash"

    print(f"Installing Coolify on {host} via SSH...")
    # Run the installation command in interactive/live mode using subprocess
    res = subprocess.run(ssh_cmd + [install_cmd], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Installation failed. Stderr:\n{res.stderr}")
        sys.exit(1)
    print("Installation command completed successfully.")
    print("Stdout output:")
    print(res.stdout)


if __name__ == "__main__":
    # Parameters matching your test_deploy setup
    install_coolify(
        host="147.224.213.171",
        user="ubuntu",
        key_file="C:/Users/dixit/Desktop/mt5 antigravity/ssh-key-2026-06-19 (1).key",
    )
