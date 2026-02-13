import os
import sys


def test_defaults_when_env_missing(monkeypatch, tmp_path):
    # Ensure current working directory is tmp_path so defaults use tmp_path
    monkeypatch.chdir(tmp_path)
    # Remove environment variables that config might use
    monkeypatch.delenv('BOT_NUMBER', raising=False)
    monkeypatch.delenv('JAVA_HOME', raising=False)
    monkeypatch.delenv('SIGNAL_CLI_CONFIG_DIR', raising=False)
    # Reload config fresh
    if 'config' in sys.modules:
        del sys.modules['config']
    import importlib
    cfg = importlib.import_module('config')
    importlib.reload(cfg)
    assert os.path.isabs(cfg.ARCHIVE_ROOT)
    assert os.path.exists(cfg.DATA_DIR)
    assert os.path.exists(cfg.LOGS_DIR)
    assert isinstance(cfg.BOT_NUMBER, str)
