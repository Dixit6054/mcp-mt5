import sys
sys.path.insert(0, 'C:/Users/dixit/Desktop/mt5 antigravity/mcp_server_code/src')

from mcp_mt5.remote_deploy import deploy_remote_instance

result = deploy_remote_instance(
    host="147.224.213.171",
    user="ubuntu",
    key_file="C:/Users/dixit/Desktop/mt5 antigravity/ssh-key-2026-06-19 (1).key",
    instance_name=".mt5_second_account",
    account_login=5052017130,
    account_password="GjOnAg@7",
    account_server="MetaQuotes-Demo",
    symbol="EURUSD",
)

print(result)
