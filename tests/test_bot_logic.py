import json
import importlib
import queue


def test_process_incoming_message_queues_and_handles_yank(tmp_env, fake_process, monkeypatch):
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    # replace request_queue with fresh queue
    q = queue.Queue()
    monkeypatch.setattr(bot, 'request_queue', q)

    msg = {
        'method': 'receive',
        'params': {
            'envelope': {
                'dataMessage': {'message': 'Yank http://example.com'},
                'source': {'uuid': 'u-1', 'number': '+100'}
            }
        }
    }
    bot.process_incoming_message(json.dumps(msg), fake_process)
    assert not q.empty()
    item = q.get_nowait()
    assert item[0].startswith('http://')


def test_process_incoming_message_stats_calls_signal(tmp_env, fake_process, monkeypatch):
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    # Prepare message
    msg = {
        'method': 'receive',
        'params': {
            'envelope': {
                'dataMessage': {'message': 'Al, stats'},
                'source': {'uuid': 'user-x', 'number': '+999'}
            }
        }
    }
    # stub stats_manager.get_formatted_stats and personality
    sm = importlib.import_module('stats_manager')
    monkeypatch.setattr(sm, 'get_formatted_stats', lambda: ('STATZ', 'user-x'))
    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_top_user_quip', lambda: 'TOPQUIP')

    bot.process_incoming_message(json.dumps(msg), fake_process)
    out = fake_process.stdin.getvalue()
    assert 'STATZ' in out
    assert 'TOPQUIP' in out


def test_handle_video_request_success_path(tmp_env, fake_process, monkeypatch, tmp_path):
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    # create fake video file to be "sent"
    v = tmp_path / 'video.mp4'
    v.write_text('x')

    # stub process_video
    def fake_process_video(url, user_id=None, progress_callback=None):
        return (str(v), 'T', 'D', None, None, 'YouTube')
    monkeypatch.setattr(vh, 'process_video', fake_process_video)

    # stub personality
    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_ack', lambda: 'ACK')
    monkeypatch.setattr(pers, 'get_quip', lambda: 'QUIP')

    # capture stats_manager.log_archive
    sm = importlib.import_module('stats_manager')
    called = {}
    def fake_log_archive(*a, **k):
        called['called'] = True
    monkeypatch.setattr(sm, 'log_archive', fake_log_archive)

    bot.handle_video_request('http://x', 'g', 'u', '+1', fake_process)
    out = fake_process.stdin.getvalue()
    assert 'ACK' in out
    assert 'QUIP' in out
    assert called.get('called', False)


def test_handle_video_request_failure_paths(tmp_env, fake_process, monkeypatch):
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    # Test DownloadError
    def raise_download(url, user_id=None, progress_callback=None):
        raise vh.DownloadError('download failed')
    monkeypatch.setattr(vh, 'process_video', raise_download)
    sm = importlib.import_module('stats_manager')
    called = {}
    def fake_log_failure(*a, **k):
        called['failure'] = True
    monkeypatch.setattr(sm, 'log_failure', fake_log_failure)

    bot.handle_video_request('http://x', 'g', 'u', '+1', fake_process)
    out = fake_process.stdin.getvalue()
    assert 'download failed' in out
    assert called.get('failure')

    # Test FileTooLargeError
    fake_process.stdin = type(fake_process.stdin)()  # reset buffer
    def raise_large(url, user_id=None, progress_callback=None):
        raise vh.FileTooLargeError('too big')
    monkeypatch.setattr(vh, 'process_video', raise_large)
    bot.handle_video_request('http://x', 'g', 'u', '+1', fake_process)
    out2 = fake_process.stdin.getvalue()
    assert 'Accordion' in out2 or 'too big' in out2
