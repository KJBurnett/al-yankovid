import json
import importlib
import os
import subprocess


def test_send_message_direct_recipient_builds_payload(fake_process):
    import signal_manager
    p = fake_process
    signal_manager.send_message(p, None, '+123', 'hello', attachments=['/tmp/a.mp4'])
    val = p.stdin.getvalue().strip()
    payload = json.loads(val)
    assert payload['method'] == 'send'
    assert payload['params']['message'] == 'hello'
    assert payload['params']['recipient'] == '+123'
    assert payload['params']['attachments'] == ['/tmp/a.mp4']


def test_send_message_group_recipient(fake_process):
    import signal_manager
    p = fake_process
    signal_manager.send_message(p, 'group-id', None, 'hi', attachments=None)
    val = p.stdin.getvalue().strip()
    payload = json.loads(val)
    assert payload['params']['groupId'] == 'group-id'
    assert 'recipient' not in payload['params']


def test_run_signal_daemon_drops_invalid_java_home(monkeypatch):
    signal_manager = importlib.import_module('signal_manager')
    importlib.reload(signal_manager)

    monkeypatch.setattr(signal_manager, 'JAVA_HOME', '/definitely/not/real')
    monkeypatch.setattr(signal_manager.os.path, 'isdir', lambda p: False)
    monkeypatch.setattr(signal_manager, 'SIGNAL_CLI_PATH', 'signal-cli')
    monkeypatch.setattr(signal_manager, 'BOT_NUMBER', '+123')

    captured = {}

    def fake_popen(*args, **kwargs):
        captured['env'] = kwargs.get('env', {})
        class P:
            stdin = None
            stdout = None
            stderr = None
            def poll(self):
                return None
        return P()

    monkeypatch.setattr(signal_manager.subprocess, 'Popen', fake_popen)
    signal_manager.run_signal_daemon()
    assert captured['env'].get('JAVA_HOME') is None


def test_run_signal_daemon_keeps_valid_java_home(monkeypatch):
    signal_manager = importlib.import_module('signal_manager')
    importlib.reload(signal_manager)

    monkeypatch.setattr(signal_manager, 'JAVA_HOME', '/valid/java/home')
    monkeypatch.setattr(signal_manager.os.path, 'isdir', lambda p: p == '/valid/java/home')
    monkeypatch.setattr(signal_manager, 'SIGNAL_CLI_PATH', 'signal-cli')
    monkeypatch.setattr(signal_manager, 'BOT_NUMBER', '+123')

    captured = {}

    def fake_popen(*args, **kwargs):
        captured['env'] = kwargs.get('env', {})
        class P:
            stdin = None
            stdout = None
            stderr = None
            def poll(self):
                return None
        return P()

    monkeypatch.setattr(signal_manager.subprocess, 'Popen', fake_popen)
    signal_manager.run_signal_daemon()
    assert captured['env'].get('JAVA_HOME') == '/valid/java/home'


def test_get_signal_cli_version_returns_first_line(monkeypatch):
    signal_manager = importlib.import_module('signal_manager')
    importlib.reload(signal_manager)

    class R:
        stdout = "signal-cli 0.14.2\nextra line\n"
        stderr = ""

    monkeypatch.setattr(signal_manager.subprocess, 'run', lambda *a, **k: R())
    version = signal_manager._get_signal_cli_version({})
    assert version == "signal-cli 0.14.2"


def test_get_signal_cli_version_returns_none_on_error(monkeypatch):
    signal_manager = importlib.import_module('signal_manager')
    importlib.reload(signal_manager)

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], output="", stderr="boom")

    monkeypatch.setattr(signal_manager.subprocess, 'run', fake_run)
    version = signal_manager._get_signal_cli_version({})
    assert version is None


def test_select_signal_config_dir_prefers_store_with_uuid_match(tmp_env, tmp_path):
    signal_manager = importlib.import_module('signal_manager')
    importlib.reload(signal_manager)

    base = tmp_path / "data"
    nested = base / "signal-cli"
    (base / "data").mkdir(parents=True, exist_ok=True)
    (nested / "data").mkdir(parents=True, exist_ok=True)

    (base / "data" / "accounts.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {"number": "+16014365901", "uuid": "abc-uuid", "path": "1", "environment": "LIVE"}
                ],
                "version": 2,
            }
        ),
        encoding="utf-8",
    )
    (nested / "data" / "accounts.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {"number": "+16014365901", "uuid": None, "path": "2", "environment": "LIVE"}
                ],
                "version": 2,
            }
        ),
        encoding="utf-8",
    )

    selected = signal_manager._select_signal_config_dir(str(base), "+16014365901")
    assert selected == str(base)


def test_select_signal_config_dir_uses_nested_when_base_has_no_match(tmp_env, tmp_path):
    signal_manager = importlib.import_module('signal_manager')
    importlib.reload(signal_manager)

    base = tmp_path / "data"
    nested = base / "signal-cli"
    (base / "data").mkdir(parents=True, exist_ok=True)
    (nested / "data").mkdir(parents=True, exist_ok=True)

    (base / "data" / "accounts.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {"number": "+19999999999", "uuid": "old", "path": "9", "environment": "LIVE"}
                ],
                "version": 2,
            }
        ),
        encoding="utf-8",
    )
    (nested / "data" / "accounts.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {"number": "+16014365901", "uuid": "new", "path": "10", "environment": "LIVE"}
                ],
                "version": 2,
            }
        ),
        encoding="utf-8",
    )

    selected = signal_manager._select_signal_config_dir(str(base), "+16014365901")
    assert selected == str(nested)
