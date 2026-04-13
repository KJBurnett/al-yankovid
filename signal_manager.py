import subprocess
import json
import time
import os
import logging
from config import JAVA_HOME, SIGNAL_CLI_PATH, BOT_NUMBER

logger = logging.getLogger("AlYankoVid.SignalManager")
LAST_SIGNAL_CONFIG_DIR = None

def _build_signal_env():
    env = os.environ.copy()
    java_home = (JAVA_HOME or "").strip()
    if not java_home:
        return env
    if os.path.isdir(java_home):
        env['JAVA_HOME'] = java_home
    else:
        # Do not force an invalid JAVA_HOME into signal-cli; allow java from PATH.
        env.pop('JAVA_HOME', None)
        logger.warning(f"Ignoring invalid JAVA_HOME path: {java_home}")
    return env

def _get_signal_cli_version(env):
    try:
        result = subprocess.run(
            [SIGNAL_CLI_PATH, '--version'],
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            timeout=10
        )
        output = (result.stdout or "").strip()
        if not output:
            output = (result.stderr or "").strip()
        if not output:
            return None
        return output.splitlines()[0].strip()
    except Exception as e:
        logger.warning(f"Could not determine signal-cli version: {e}")
        return None

def _read_accounts(config_dir):
    accounts_path = os.path.join(config_dir, 'data', 'accounts.json')
    if not os.path.exists(accounts_path):
        return []
    try:
        with open(accounts_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        return payload.get('accounts', []) or []
    except Exception:
        return []

def _score_config_dir(config_dir, bot_number):
    accounts = _read_accounts(config_dir)
    matched = [a for a in accounts if a.get('number') == bot_number]
    matched_with_uuid = [a for a in matched if a.get('uuid')]
    return {
        "config_dir": config_dir,
        "accounts": accounts,
        "matched": matched,
        "matched_with_uuid": matched_with_uuid,
    }

def _select_signal_config_dir(base_config_dir, bot_number):
    candidates = [base_config_dir]
    nested = os.path.join(base_config_dir, 'signal-cli')
    if os.path.isdir(nested):
        candidates.append(nested)

    scored = [_score_config_dir(c, bot_number) for c in candidates]
    for s in scored:
        logger.info(
            "Signal config candidate: %s (accounts=%d, matched=%d, matched_with_uuid=%d)",
            s["config_dir"],
            len(s["accounts"]),
            len(s["matched"]),
            len(s["matched_with_uuid"]),
        )

    def sort_key(item):
        return (
            len(item["matched_with_uuid"]),
            len(item["matched"]),
            len(item["accounts"]),
        )

    selected = sorted(scored, key=sort_key, reverse=True)[0]
    logger.info("Selected Signal config directory: %s", selected["config_dir"])
    return selected["config_dir"]

def get_last_signal_config_dir():
    return LAST_SIGNAL_CONFIG_DIR

def run_signal_daemon():
    """Runs signal-cli in json-rpc mode."""
    env = _build_signal_env()
    signal_version = _get_signal_cli_version(env)
    if signal_version:
        logger.info(f"Using signal-cli version: {signal_version}")

    # Determine config directory for signal-cli. Prefer SIGNAL_CLI_CONFIG_DIR env var.
    base_config_dir = env.get('SIGNAL_CLI_CONFIG_DIR', '/app/data')
    config_dir = _select_signal_config_dir(base_config_dir, BOT_NUMBER)
    global LAST_SIGNAL_CONFIG_DIR
    LAST_SIGNAL_CONFIG_DIR = config_dir

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
