import pytest
import io
import os
import sys

# Ensure repository root is in sys.path so tests can import project modules even when cwd changes
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)


def _make_completed(stdout='', stderr='', returncode=0):
    class Completed:
        def __init__(self, stdout, stderr, returncode):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode
    return Completed(stdout, stderr, returncode)


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    import config
    # Patch config paths to use tmp_path
    monkeypatch.setattr(config, 'ARCHIVE_ROOT', str(tmp_path / 'archive'))
    monkeypatch.setattr(config, 'DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setattr(config, 'STATS_FILE', str(tmp_path / 'data' / 'stats.json'))
    monkeypatch.setattr(config, 'USERS_MAP_FILE', str(tmp_path / 'data' / 'users_map.json'))
    monkeypatch.setattr(config, 'LOGS_DIR', str(tmp_path / 'logs'))
    # Ensure directories exist
    os.makedirs(config.ARCHIVE_ROOT, exist_ok=True)
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    yield


@pytest.fixture
def fake_process():
    class FakeStdin(io.StringIO):
        def flush(self):
            return super().flush()

    class FakeProcess:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = io.StringIO()
            self.stderr = io.StringIO()

        def poll(self):
            return None

    return FakeProcess()


@pytest.fixture
def make_subprocess_result():
    return _make_completed
