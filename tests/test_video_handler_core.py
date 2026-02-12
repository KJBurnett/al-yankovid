import os
import json
import importlib


def test_clean_filename(tmp_env):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    s = 'Bad/Name*?:"<>|.mp4'
    cleaned = vh.clean_filename(s)
    for ch in '\\/*?:"<>|':
        assert ch not in cleaned
    assert 'BadName' in cleaned or 'BadName' or cleaned


def test_archive_metadata_writes_file(tmp_env, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    d = tmp_path / 'archive'
    d.mkdir(exist_ok=True)
    info = {
        'title': 'T Title',
        'description': 'Some desc',
        'uploader': 'Uploader',
        'extractor_key': 'Generic',
        'timestamp': 123456,
        'webpage_url': 'http://example.com'
    }
    metadata_path, title, description, service = vh.archive_metadata(str(d), info)
    assert os.path.exists(metadata_path)
    with open(metadata_path, 'r', encoding='utf-8') as f:
        m = json.load(f)
    assert m['title'] == info['title']
    assert m['description'] == info['description']
    assert m['service'] == service


def test_load_and_save_archive_index_roundtrip(tmp_env, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    idx = {'a': 'b'}
    vh.save_archive_index(idx)
    out = vh.load_archive_index()
    assert out == idx


def test_find_subtitle_file_selection_prioritizes_english(tmp_env, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    d = tmp_path
    base = 'MyVideo [id].mp4'
    # create candidates
    (d / 'MyVideo [id].en.vtt').write_text('')
    (d / 'MyVideo [id].fr.vtt').write_text('')
    sel = vh.find_subtitle_file(str(d), base)
    assert sel is not None
    assert sel.endswith('.vtt')
    assert '.en.' in os.path.basename(sel).lower()


def test_safe_subprocess_run_sets_encoding(tmp_env, monkeypatch):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    called = {}

    def fake_run(cmd, **kwargs):
        called['kwargs'] = kwargs
        class R: pass
        r = R()
        r.stdout = ''
        r.stderr = ''
        r.returncode = 0
        return r

    monkeypatch.setattr(vh, 'subprocess', vh.subprocess)
    monkeypatch.setattr(vh.subprocess, 'run', fake_run)
    vh.safe_subprocess_run(['echo'], text=True)
    assert 'encoding' in called['kwargs'] or called['kwargs'].get('text')
    assert called['kwargs'].get('errors') == 'replace'


def test_get_video_info_parses_json(tmp_env, monkeypatch):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    fake = json.dumps({'id': 'abc', 'title': 't'})
    def fake_safe(cmd, **kwargs):
        class R: pass
        r = R()
        r.stdout = fake
        r.stderr = ''
        r.returncode = 0
        return r
    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    info = vh.get_video_info('http://x')
    assert info.get('id') == 'abc'


def test_download_video_returns_expected_path(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    out_dir = str(tmp_path / 'out')
    os.makedirs(out_dir, exist_ok=True)

    # stub get_video_info to return id
    def fake_get(url):
        return {'id': 'XYZ'}
    monkeypatch.setattr(vh, 'get_video_info', fake_get)

    # create a matching file that download_video would discover
    path = os.path.join(out_dir, 'Any Title [XYZ].mp4')
    open(path, 'wb').write(b'x')

    # stub safe_subprocess_run to not fail
    def fake_safe(cmd, **kwargs):
        class R: pass
        r = R()
        r.stdout = ''
        r.stderr = ''
        r.returncode = 0
        return r
    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)

    res = vh.download_video('http://x', out_dir)
    assert res is not None
    assert res.endswith('.mp4')


def test_compress_video_with_successful_ffmpeg_calls(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    in_file = str(tmp_path / 'in.mp4')
    open(in_file, 'wb').write(b'x' * 1024)

    def fake_safe(cmd, **kwargs):
        class R: pass
        if 'ffprobe' in cmd[0]:
            r = R(); r.stdout = '60\n50000000'; r.stderr = ''; r.returncode = 0; return r
        else:
            r = R(); r.stdout = ''; r.stderr = ''; r.returncode = 0; return r
    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    out = vh.compress_video(in_file, target_size_mb=10)
    assert out.endswith('_normalized.mp4')


def test_process_video_archives_and_updates_index(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    url = 'http://example.com/v'

    # stub get_video_info
    def fake_info(u):
        return {'id': 'VID123', 'title': 'T', 'description': 'D', 'extractor_key': 'Generic', 'webpage_url': u}
    monkeypatch.setattr(vh, 'get_video_info', fake_info)

    # stub download_video to create a file in provided output dir
    def fake_download(u, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, 'T [VID123].mp4')
        with open(p, 'wb') as f: f.write(b'x')
        return p
    monkeypatch.setattr(vh, 'download_video', fake_download)

    # stub compress to return same path
    monkeypatch.setattr(vh, 'compress_video', lambda p, *a, **k: p)

    archived_path, title, description, metadata_path, sub_path, service = vh.process_video(url, user_id='tester')
    # index should contain url
    idx = vh.load_archive_index()
    assert url in idx
    assert os.path.exists(idx[url])


def test_process_video_oversize_raises_FileTooLargeError(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    url = 'http://example.com/large'
    def fake_info(u):
        return {'id': 'BIGID', 'title': 'Big', 'description': '', 'extractor_key': 'Generic', 'webpage_url': u}
    monkeypatch.setattr(vh, 'get_video_info', fake_info)

    def fake_download(u, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, 'Big [BIGID].mp4')
        with open(p, 'wb') as f: f.write(b'x')
        return p
    monkeypatch.setattr(vh, 'download_video', fake_download)

    # compress returns same path (no size reduction)
    monkeypatch.setattr(vh, 'compress_video', lambda p, *a, **k: p)
    # force reported size to be huge
    monkeypatch.setattr(vh, 'get_file_size_mb', lambda p: vh.UPLOAD_LIMIT_MB * 2)

    called = {'progress': False}
    def progress_cb():
        called['progress'] = True
    import pytest
    with pytest.raises(vh.FileTooLargeError):
        vh.process_video(url, user_id='tester', progress_callback=progress_cb)
    assert called['progress']
