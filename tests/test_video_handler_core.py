import os
import json
import importlib
import sys
import subprocess


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


def test_resolve_ytdlp_cmd_falls_back_to_python_module(tmp_env, monkeypatch):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    def fake_safe(cmd, **kwargs):
        assert cmd == [sys.executable, '-m', 'yt_dlp', '--version']
        class R: pass
        r = R()
        r.stdout = '2026.01.01'
        r.stderr = ''
        r.returncode = 0
        return r

    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    monkeypatch.setattr(vh, 'which', lambda name: None)
    monkeypatch.setattr(vh.os.path, 'exists', lambda path: path == sys.executable)

    cmd = vh.resolve_ytdlp_cmd()
    assert cmd == [sys.executable, '-m', 'yt_dlp']


def test_has_audio_stream_detects_audio(tmp_env, monkeypatch):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    def fake_safe(cmd, **kwargs):
        class R: pass
        r = R()
        r.stdout = '0\n'
        r.stderr = ''
        r.returncode = 0
        return r

    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    assert vh.has_audio_stream('/tmp/video.mp4') is True


def test_has_audio_stream_detects_silence(tmp_env, monkeypatch):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    def fake_safe(cmd, **kwargs):
        class R: pass
        r = R()
        r.stdout = ''
        r.stderr = ''
        r.returncode = 0
        return r

    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    assert vh.has_audio_stream('/tmp/video.mp4') is False


def test_download_video_prefers_first_audio_selector(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    out_dir = str(tmp_path / 'out')
    os.makedirs(out_dir, exist_ok=True)

    def fake_get(url):
        return {'id': 'XYZ'}
    monkeypatch.setattr(vh, 'get_video_info', fake_get)
    monkeypatch.setattr(vh, 'resolve_ytdlp_cmd', lambda: ['yt-dlp'])

    seen_selectors = []

    def fake_safe(cmd, **kwargs):
        if '-f' in cmd:
            selector = cmd[cmd.index('-f') + 1]
            seen_selectors.append(selector)
            path = os.path.join(out_dir, 'Any Title [XYZ].mp4')
            with open(path, 'wb') as f:
                f.write(b'x')
        class R: pass
        r = R()
        r.stdout = ''
        r.stderr = ''
        r.returncode = 0
        return r
    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    monkeypatch.setattr(vh, 'has_audio_stream', lambda p: True)

    res = vh.download_video('http://x', out_dir)
    assert res is not None
    assert res.endswith('.mp4')
    assert seen_selectors == [vh.FORMAT_SELECTORS[0]]


def test_download_video_retries_when_first_attempt_silent(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    out_dir = str(tmp_path / 'out')
    os.makedirs(out_dir, exist_ok=True)

    monkeypatch.setattr(vh, 'get_video_info', lambda url: {'id': 'XYZ'})
    monkeypatch.setattr(vh, 'resolve_ytdlp_cmd', lambda: ['yt-dlp'])

    seen_selectors = []
    created_paths = []

    def fake_safe(cmd, **kwargs):
        if '-f' in cmd:
            selector = cmd[cmd.index('-f') + 1]
            seen_selectors.append(selector)
            path = os.path.join(out_dir, f'Any Title [XYZ]_{len(seen_selectors)}.mp4')
            created_paths.append(path)
            with open(path, 'wb') as f:
                f.write(b'x')
        class R: pass
        r = R()
        r.stdout = ''
        r.stderr = ''
        r.returncode = 0
        return r

    has_audio_results = [False, True]
    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    monkeypatch.setattr(vh, 'has_audio_stream', lambda p: has_audio_results.pop(0))

    res = vh.download_video('http://x', out_dir)
    assert res is not None
    assert os.path.exists(res)
    assert len(seen_selectors) == 2
    assert seen_selectors[0] == vh.FORMAT_SELECTORS[0]
    assert seen_selectors[1] == vh.FORMAT_SELECTORS[1]
    assert not os.path.exists(created_paths[0])
    assert os.path.exists(created_paths[1])


def test_download_video_instagram_style_fallback_to_audio_pair(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    out_dir = str(tmp_path / 'out')
    os.makedirs(out_dir, exist_ok=True)

    monkeypatch.setattr(vh, 'get_video_info', lambda url: {'id': 'IG123'})
    monkeypatch.setattr(vh, 'resolve_ytdlp_cmd', lambda: ['yt-dlp'])

    selectors_seen = []
    probe_paths = []

    def fake_safe(cmd, **kwargs):
        if '-f' in cmd:
            selector = cmd[cmd.index('-f') + 1]
            selectors_seen.append(selector)
            path = os.path.join(out_dir, f'Video [IG123]_{len(selectors_seen)}.mp4')
            with open(path, 'wb') as f:
                f.write(b'x')
        class R: pass
        r = R()
        r.stdout = ''
        r.stderr = ''
        r.returncode = 0
        return r

    def fake_has_audio(path):
        probe_paths.append(path)
        # Simulate Instagram failure: first selector yields silent video-only stream.
        return len(probe_paths) >= 2

    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    monkeypatch.setattr(vh, 'has_audio_stream', fake_has_audio)

    res = vh.download_video('https://www.instagram.com/reel/abc/', out_dir)
    assert res is not None
    assert len(selectors_seen) == 2
    assert selectors_seen[:2] == vh.FORMAT_SELECTORS[:2]


def test_download_video_all_silent_returns_last_attempt_file(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    out_dir = str(tmp_path / 'out')
    os.makedirs(out_dir, exist_ok=True)

    monkeypatch.setattr(vh, 'get_video_info', lambda url: {'id': 'XYZ'})
    monkeypatch.setattr(vh, 'resolve_ytdlp_cmd', lambda: ['yt-dlp'])

    created_paths = []

    def fake_safe(cmd, **kwargs):
        if '-f' in cmd:
            path = os.path.join(out_dir, f'Any Title [XYZ]_{len(created_paths)}.mp4')
            created_paths.append(path)
            with open(path, 'wb') as f:
                f.write(b'x')
        class R: pass
        r = R()
        r.stdout = ''
        r.stderr = ''
        r.returncode = 0
        return r

    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    monkeypatch.setattr(vh, 'has_audio_stream', lambda p: False)

    res = vh.download_video('http://x', out_dir)
    assert res is not None
    assert os.path.exists(res)
    assert res == created_paths[-1]

def test_download_video_retries_selector_without_subtitles_on_subtitle_error(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    out_dir = str(tmp_path / 'out')
    os.makedirs(out_dir, exist_ok=True)

    monkeypatch.setattr(vh, 'get_video_info', lambda url: {'id': 'XYZ'})
    monkeypatch.setattr(vh, 'resolve_ytdlp_cmd', lambda: ['yt-dlp'])

    calls = []

    def fake_safe(cmd, **kwargs):
        calls.append(cmd)
        class R: pass
        if '--write-subs' in cmd:
            raise subprocess.CalledProcessError(
                1, cmd, output='', stderr="ERROR: Unable to download video subtitles for 'ab': HTTP Error 429: Too Many Requests"
            )
        path = os.path.join(out_dir, 'Any Title [XYZ].mp4')
        with open(path, 'wb') as f:
            f.write(b'x')
        r = R()
        r.stdout = ''
        r.stderr = ''
        r.returncode = 0
        return r

    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    monkeypatch.setattr(vh, 'has_audio_stream', lambda p: True)

    res = vh.download_video('http://x', out_dir, format_selectors=[vh.FORMAT_SELECTORS[0]])
    assert res is not None
    assert os.path.exists(res)
    assert len(calls) == 2
    assert '--write-subs' in calls[0]
    assert '--write-subs' not in calls[1]


def test_download_video_skips_unavailable_formats_and_falls_back(tmp_env, monkeypatch, tmp_path):
    """Regression: when early format selectors fail with 'Requested format is not available'
    (as TikTok does for bestvideo+bestaudio), the loop must continue to the next selector
    instead of raising immediately.
    """
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    out_dir = str(tmp_path / 'out')
    os.makedirs(out_dir, exist_ok=True)

    monkeypatch.setattr(vh, 'get_video_info', lambda url: {'id': 'TK999'})
    monkeypatch.setattr(vh, 'resolve_ytdlp_cmd', lambda: ['yt-dlp'])

    selectors_tried = []

    def fake_safe(cmd, **kwargs):
        if '-f' in cmd:
            selector = cmd[cmd.index('-f') + 1]
            selectors_tried.append(selector)
            # Simulate TikTok: first two selectors unavailable, 'best' succeeds.
            if selector in ('bestvideo+bestaudio', 'best[acodec!=none]'):
                raise subprocess.CalledProcessError(
                    1, cmd, output='',
                    stderr='ERROR: Requested format is not available. Use --list-formats for a list of available formats'
                )
            path = os.path.join(out_dir, 'TikTok Video [TK999].mp4')
            with open(path, 'wb') as f:
                f.write(b'x')
        class R: pass
        r = R()
        r.stdout = ''
        r.stderr = ''
        r.returncode = 0
        return r

    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    monkeypatch.setattr(vh, 'has_audio_stream', lambda p: True)

    res = vh.download_video('https://www.tiktok.com/t/ZP8gUYuFD/', out_dir)
    assert res is not None, "Expected a file but got None"
    assert os.path.exists(res), f"Expected file at {res!r} to exist"
    assert 'TK999' in res, "Expected video ID in filename"
    # The first two selectors should have been tried and skipped, then a successful one used.
    assert selectors_tried[0] == 'bestvideo+bestaudio'
    assert selectors_tried[1] == 'best[acodec!=none]'
    assert len(selectors_tried) >= 3


def test_compress_video_with_successful_ffmpeg_calls(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    in_file = str(tmp_path / 'in.mp4')
    open(in_file, 'wb').write(b'x' * 1024)
    commands = []

    def fake_safe(cmd, **kwargs):
        commands.append(cmd)
        class R: pass
        if 'ffprobe' in cmd[0]:
            r = R(); r.stdout = '60\n50000000'; r.stderr = ''; r.returncode = 0; return r
        else:
            r = R(); r.stdout = ''; r.stderr = ''; r.returncode = 0; return r
    monkeypatch.setattr(vh, 'safe_subprocess_run', fake_safe)
    out = vh.compress_video(in_file, target_size_mb=10)
    assert out.endswith('_normalized.mp4')
    pass1 = commands[1]
    pass2 = commands[2]
    assert pass1[:5] == ['ffmpeg', '-y', '-i', in_file, '-map']
    assert '-an' in pass1
    assert '-map' in pass2
    assert '0:a:0?' in pass2
    assert '-c:a' in pass2
    assert '-ac' in pass2
    assert '-ar' in pass2


def test_process_video_archives_and_updates_index(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    url = 'http://example.com/v'

    # stub get_video_info
    def fake_info(u):
        return {'id': 'VID123', 'title': 'T', 'description': 'D', 'extractor_key': 'Generic', 'webpage_url': u}
    monkeypatch.setattr(vh, 'get_video_info', fake_info)

    # stub download_video to create a file in provided output dir
    def fake_download(u, out_dir, **kwargs):
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, 'T [VID123].mp4')
        with open(p, 'wb') as f: f.write(b'x')
        return p
    monkeypatch.setattr(vh, 'download_video', fake_download)

    # stub compress to return same path
    monkeypatch.setattr(vh, 'compress_video', lambda p, *a, **k: p)

    monkeypatch.setattr(vh, 'has_audio_stream', lambda p: True)

    archived_path, title, description, metadata_path, sub_path, service, has_audio = vh.process_video(url, user_id='tester')
    # index should contain url
    idx = vh.load_archive_index()
    assert url in idx
    assert os.path.exists(idx[url])
    assert has_audio is True


def test_process_video_oversize_raises_FileTooLargeError(tmp_env, monkeypatch, tmp_path):
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    url = 'http://example.com/large'
    def fake_info(u):
        return {'id': 'BIGID', 'title': 'Big', 'description': '', 'extractor_key': 'Generic', 'webpage_url': u}
    monkeypatch.setattr(vh, 'get_video_info', fake_info)

    def fake_download(u, out_dir, **kwargs):
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
