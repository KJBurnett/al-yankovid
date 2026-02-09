import subprocess
import json
import time
import os
import logging
from config import JAVA_HOME, SIGNAL_CLI_PATH, BOT_NUMBER

logger = logging.getLogger("AlYankoVid.SignalManager")

def run_signal_daemon():
    """Runs signal-cli in json-rpc mode."""
    env = os.environ.copy()
    env['JAVA_HOME'] = JAVA_HOME

    # Determine config directory for signal-cli. Prefer SIGNAL_CLI_CONFIG_DIR env var.
    config_dir = env.get('SIGNAL_CLI_CONFIG_DIR', '/app/data')
    # If the config_dir contains a nested 'signal-cli' folder (common when copying), point to that.
    nested = os.path.join(config_dir, 'signal-cli')
    if os.path.isdir(nested):
        config_dir = nested

    command = [SIGNAL_CLI_PATH, '--config', config_dir, '-u', BOT_NUMBER, 'jsonRpc']

    creationflags = 0
    if os.name == 'nt':
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(
        command, 
        stdin=subprocess.PIPE, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE,
        text=True, 
        encoding='utf-8',
        env=env,
        bufsize=1,
        creationflags=creationflags
    )
    return process

def send_message(process, recipient_group, recipient_number, message, attachments=None):
    """Sends a message via JSON-RPC."""
    if not process or process.poll() is not None:
        logger.error("Cannot send message: Signal daemon is not running.")
        return

    payload = {
        "jsonrpc": "2.0",
        "method": "send",
        "params": {
            "message": message,
        },
        "id": int(time.time() * 1000)
    }
    
    if recipient_group:
        payload["params"]["groupId"] = recipient_group
    elif recipient_number:
        payload["params"]["recipient"] = recipient_number
        
    if attachments:
        payload["params"]["attachments"] = attachments
        
    try:
        json_payload = json.dumps(payload)
        process.stdin.write(json_payload + "\n")
        process.stdin.flush()
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
