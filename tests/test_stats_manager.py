import os
import sys
import json


def _reload_stats_manager():
    if 'stats_manager' in sys.modules:
        del sys.modules['stats_manager']
    import importlib
    return importlib.import_module('stats_manager')


def test_log_archive_creates_entry(tmp_env, tmp_path):
    sm = _reload_stats_manager()
    user_uuid = 'user-1'
    user_number = '+111'
    url = 'http://example.com/video'
    filepath = tmp_path / 'file.mp4'
    filepath.write_text('x')
    sm.log_archive(user_uuid, user_number, url, str(filepath))
    assert os.path.exists(sm.STATS_FILE)
    with open(sm.STATS_FILE, 'r') as f:
        data = json.load(f)
    assert user_uuid in data['users']
    assert any(a['url'] == url for a in data['users'][user_uuid]['archives'])


def test_log_failure_creates_failure_entry(tmp_env, tmp_path):
    sm = _reload_stats_manager()
    user_uuid = 'user-2'
    user_number = '+222'
    url = 'http://example.com/fail'
    sm.log_failure(user_uuid, user_number, url, 'oops')
    with open(sm.STATS_FILE) as f:
        data = json.load(f)
    assert user_uuid in data['users']
    assert any(f['url'] == url and f['error'] == 'oops' for f in data['users'][user_uuid]['failures'])


def test_delete_archive_removes_files_and_updates_index_and_stats(tmp_env, tmp_path):
    sm = _reload_stats_manager()
    # Create archive dir structure
    folder = tmp_path / 'archive' / 'user1' / 'ts'
    folder.mkdir(parents=True)
    video = folder / 'video.mp4'
    video.write_text('x')
    url = 'http://example.com/to_delete'
    # create index.json in ARCHIVE_ROOT
    arch_root = sm.ARCHIVE_ROOT
    os.makedirs(arch_root, exist_ok=True)
    index_path = os.path.join(arch_root, 'index.json')
    with open(index_path, 'w') as f:
        json.dump({url: str(video)}, f)
    # create stats file with archives entry
    os.makedirs(os.path.dirname(sm.STATS_FILE), exist_ok=True)
    with open(sm.STATS_FILE, 'w') as f:
        json.dump({"users": {"user1": {"archives": [{"url": url, "filepath": str(video)}], "failures": []}}}, f)
    res = sm.delete_archive(url)
    assert res
    # ensure folder removed
    assert not folder.exists()
    # ensure index updated
    with open(index_path, 'r') as f:
        idx = json.load(f)
    assert url not in idx
    # ensure stats updated
    with open(sm.STATS_FILE, 'r') as f:
        stats = json.load(f)
    for data in stats.get('users', {}).values():
        assert all(a.get('url') != url for a in data.get('archives', []))
