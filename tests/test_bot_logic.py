import json
import importlib
import queue
import threading

from transports import YankRequest, SignalReplyContext


def test_process_incoming_message_queues_and_handles_yank(tmp_env, fake_process, monkeypatch):
    bot = importlib.import_module('bot')
    importlib.reload(bot)
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
    req = q.get_nowait()
    assert req.url.startswith('http://')


def test_process_incoming_message_stats_calls_signal(tmp_env, fake_process, monkeypatch):
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    msg = {
        'method': 'receive',
        'params': {
            'envelope': {
                'dataMessage': {'message': 'Al, stats'},
                'source': {'uuid': 'user-x', 'number': '+999'}
            }
        }
    }
    sm = importlib.import_module('stats_manager')
    monkeypatch.setattr(sm, 'get_formatted_stats', lambda: ('STATZ', 'user-x'))
    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_top_user_quip', lambda: 'TOPQUIP')

    bot.process_incoming_message(json.dumps(msg), fake_process)
    out = fake_process.stdin.getvalue()
    assert 'STATZ' in out
    assert 'TOPQUIP' in out


def test_handle_video_request_success_path(tmp_env, fake_process, monkeypatch, tmp_path, make_signal_req):
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    v = tmp_path / 'video.mp4'
    v.write_text('x')

    def fake_process_video(url, user_id=None, progress_callback=None, retry_callback=None,
                           upload_limit_mb=None, service=None):
        return (str(v), 'T', 'D', None, None, 'YouTube', True)
    monkeypatch.setattr(vh, 'process_video', fake_process_video)

    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_ack', lambda: 'ACK')
    monkeypatch.setattr(pers, 'get_quip', lambda: 'QUIP')

    sm = importlib.import_module('stats_manager')
    called = {}
    def fake_log_archive(*a, **k):
        called['called'] = True
    monkeypatch.setattr(sm, 'log_archive', fake_log_archive)

    req = make_signal_req('http://x', group_id='g', user_id='u', source_id='+1')
    bot.handle_video_request(req)
    out = fake_process.stdin.getvalue()
    assert 'ACK' in out
    assert 'QUIP' in out
    assert called.get('called', False)


def test_handle_video_request_mentions_silent_video(tmp_env, fake_process, monkeypatch, tmp_path, make_signal_req):
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    v = tmp_path / 'video.mp4'
    v.write_text('x')

    def fake_process_video(url, user_id=None, progress_callback=None, retry_callback=None,
                           upload_limit_mb=None, service=None):
        return (str(v), 'T', 'D', None, None, 'TikTok', False)
    monkeypatch.setattr(vh, 'process_video', fake_process_video)

    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_ack', lambda: 'ACK')
    monkeypatch.setattr(pers, 'get_quip', lambda: 'QUIP')

    sm = importlib.import_module('stats_manager')
    monkeypatch.setattr(sm, 'log_archive', lambda *a, **k: None)

    req = make_signal_req('http://x', group_id='g', user_id='u', source_id='+1')
    bot.handle_video_request(req)
    out = fake_process.stdin.getvalue()
    assert 'came through without an audio stream' in out


def test_handle_video_request_failure_paths(tmp_env, fake_process, monkeypatch, make_signal_req):
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    def raise_download(url, user_id=None, progress_callback=None, retry_callback=None,
                       upload_limit_mb=None, service=None):
        raise vh.DownloadError('download failed')
    monkeypatch.setattr(vh, 'process_video', raise_download)
    sm = importlib.import_module('stats_manager')
    called = {}
    def fake_log_failure(*a, **k):
        called['failure'] = True
    monkeypatch.setattr(sm, 'log_failure', fake_log_failure)

    req = make_signal_req('http://x', group_id='g', user_id='u', source_id='+1')
    bot.handle_video_request(req)
    out = fake_process.stdin.getvalue()
    assert 'download failed' in out
    assert called.get('failure')

    # Test FileTooLargeError
    fake_process.stdin = type(fake_process.stdin)()  # reset buffer
    def raise_large(url, user_id=None, progress_callback=None, retry_callback=None,
                    upload_limit_mb=None, service=None):
        raise vh.FileTooLargeError('too big')
    monkeypatch.setattr(vh, 'process_video', raise_large)
    req2 = make_signal_req('http://x', group_id='g', user_id='u', source_id='+1')
    bot.handle_video_request(req2)
    out2 = fake_process.stdin.getvalue()
    assert 'Accordion' in out2 or 'too big' in out2


# --- Multi-URL / Batch Tests ---

def test_single_url_queues_with_no_batch_id(tmp_env, fake_process, monkeypatch):
    """Single URL is queued as a YankRequest with batch_id=None."""
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    q = queue.Queue()
    monkeypatch.setattr(bot, 'request_queue', q)

    msg = {
        'method': 'receive',
        'params': {'envelope': {
            'dataMessage': {'message': 'Yank http://example.com'},
            'source': {'uuid': 'u-1', 'number': '+100'}
        }}
    }
    bot.process_incoming_message(json.dumps(msg), fake_process)

    req = q.get_nowait()
    assert req.url == 'http://example.com'
    assert req.batch_id is None


def test_multi_url_inline_spaces_queues_batch(tmp_env, fake_process, monkeypatch):
    """Space-separated URLs in a yank command are queued as a batch."""
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    q = queue.Queue()
    monkeypatch.setattr(bot, 'request_queue', q)
    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_batch_ack', lambda count: f'BATCH_ACK_{count}')

    msg = {
        'method': 'receive',
        'params': {'envelope': {
            'dataMessage': {'message': 'Yank http://a.com http://b.com http://c.com'},
            'source': {'uuid': 'u-1', 'number': '+100'}
        }}
    }
    bot.process_incoming_message(json.dumps(msg), fake_process)

    assert q.qsize() == 3
    items = [q.get_nowait() for _ in range(3)]
    assert {i.url for i in items} == {'http://a.com', 'http://b.com', 'http://c.com'}
    batch_ids = [i.batch_id for i in items]
    assert batch_ids[0] == batch_ids[1] == batch_ids[2]
    assert batch_ids[0] is not None
    assert 'BATCH_ACK_3' in fake_process.stdin.getvalue()


def test_multi_url_commas_queues_batch(tmp_env, fake_process, monkeypatch):
    """Comma-separated URLs are extracted and queued as a batch."""
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    q = queue.Queue()
    monkeypatch.setattr(bot, 'request_queue', q)
    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_batch_ack', lambda count: f'BATCH_ACK_{count}')

    msg = {
        'method': 'receive',
        'params': {'envelope': {
            'dataMessage': {'message': 'Yank http://a.com,http://b.com'},
            'source': {'uuid': 'u-1', 'number': '+100'}
        }}
    }
    bot.process_incoming_message(json.dumps(msg), fake_process)

    assert q.qsize() == 2
    items = [q.get_nowait() for _ in range(2)]
    assert {i.url for i in items} == {'http://a.com', 'http://b.com'}
    assert 'BATCH_ACK_2' in fake_process.stdin.getvalue()


def test_multi_url_newlines_queues_batch(tmp_env, fake_process, monkeypatch):
    """Newline-separated URLs are extracted and queued as a batch."""
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    q = queue.Queue()
    monkeypatch.setattr(bot, 'request_queue', q)
    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_batch_ack', lambda count: f'BATCH_ACK_{count}')

    msg = {
        'method': 'receive',
        'params': {'envelope': {
            'dataMessage': {'message': 'Yank\nhttp://a.com\nhttp://b.com'},
            'source': {'uuid': 'u-1', 'number': '+100'}
        }}
    }
    bot.process_incoming_message(json.dumps(msg), fake_process)

    assert q.qsize() == 2
    assert 'BATCH_ACK_2' in fake_process.stdin.getvalue()


def test_multi_url_mixed_separators_queues_batch(tmp_env, fake_process, monkeypatch):
    """Mixed separators (comma, space, newline) all parsed correctly."""
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    q = queue.Queue()
    monkeypatch.setattr(bot, 'request_queue', q)
    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_batch_ack', lambda count: f'BATCH_ACK_{count}')

    msg = {
        'method': 'receive',
        'params': {'envelope': {
            'dataMessage': {'message': 'Yank http://a.com,  http://b.com\nhttp://c.com'},
            'source': {'uuid': 'u-1', 'number': '+100'}
        }}
    }
    bot.process_incoming_message(json.dumps(msg), fake_process)

    assert q.qsize() == 3
    assert 'BATCH_ACK_3' in fake_process.stdin.getvalue()


def test_record_batch_result_no_summary_until_last(tmp_env, fake_process, monkeypatch, make_signal_req):
    """Summary message is not sent until every URL in the batch has a result."""
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_batch_complete', lambda: 'BATCH_DONE')

    batch_id = 'test-batch-abc'
    ctx = SignalReplyContext(
        process=fake_process, group_id='g', recipient_number='+1',
        user_id='u', source_id='+1',
    )
    bot.batch_state[batch_id] = {
        'total': 3,
        'results': [],
        'reply_context': ctx,
        'user_id': 'u',
    }

    bot._record_batch_result(batch_id, 'http://a.com', True)
    assert 'BATCH_DONE' not in fake_process.stdin.getvalue()

    bot._record_batch_result(batch_id, 'http://b.com', False)
    assert 'BATCH_DONE' not in fake_process.stdin.getvalue()

    bot._record_batch_result(batch_id, 'http://c.com', True)
    out = fake_process.stdin.getvalue()
    assert 'BATCH_DONE' in out
    assert '\\u2705 http://a.com' in out  # ✅
    assert '\\u274c http://b.com' in out  # ❌
    assert '\\u2705 http://c.com' in out  # ✅
    assert batch_id not in bot.batch_state  # cleaned up


def test_handle_video_request_records_success_in_batch(tmp_env, fake_process, monkeypatch, tmp_path, make_signal_req):
    """Successful video request with batch_id sends ✅ in final summary."""
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    v = tmp_path / 'video.mp4'
    v.write_text('x')

    def fake_process_video(url, user_id=None, progress_callback=None, retry_callback=None,
                           upload_limit_mb=None, service=None):
        return (str(v), 'T', 'D', None, None, 'YouTube', True)
    monkeypatch.setattr(vh, 'process_video', fake_process_video)

    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_ack', lambda: 'ACK')
    monkeypatch.setattr(pers, 'get_quip', lambda: 'QUIP')
    monkeypatch.setattr(pers, 'get_batch_complete', lambda: 'BATCH_DONE')
    sm = importlib.import_module('stats_manager')
    monkeypatch.setattr(sm, 'log_archive', lambda *a, **k: None)

    batch_id = 'success-batch'
    ctx = SignalReplyContext(
        process=fake_process, group_id='g', recipient_number='+1',
        user_id='u', source_id='+1',
    )
    bot.batch_state[batch_id] = {
        'total': 1, 'results': [], 'reply_context': ctx, 'user_id': 'u',
    }

    req = make_signal_req('http://x.com', group_id='g', user_id='u', source_id='+1', batch_id=batch_id)
    bot.handle_video_request(req)

    out = fake_process.stdin.getvalue()
    assert 'BATCH_DONE' in out
    assert '\\u2705 http://x.com' in out  # ✅ JSON-escaped


def test_handle_video_request_records_failure_in_batch(tmp_env, fake_process, monkeypatch, make_signal_req):
    """Failed video request with batch_id sends ❌ in final summary."""
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    def raise_download(url, user_id=None, progress_callback=None, retry_callback=None,
                       upload_limit_mb=None, service=None):
        raise vh.DownloadError('oops')
    monkeypatch.setattr(vh, 'process_video', raise_download)

    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_ack', lambda: 'ACK')
    monkeypatch.setattr(pers, 'get_batch_complete', lambda: 'BATCH_DONE')
    sm = importlib.import_module('stats_manager')
    monkeypatch.setattr(sm, 'log_failure', lambda *a, **k: None)

    batch_id = 'failure-batch'
    ctx = SignalReplyContext(
        process=fake_process, group_id='g', recipient_number='+1',
        user_id='u', source_id='+1',
    )
    bot.batch_state[batch_id] = {
        'total': 1, 'results': [], 'reply_context': ctx, 'user_id': 'u',
    }

    req = make_signal_req('http://x.com', group_id='g', user_id='u', source_id='+1', batch_id=batch_id)
    bot.handle_video_request(req)

    out = fake_process.stdin.getvalue()
    assert 'BATCH_DONE' in out
    assert '\\u274c http://x.com' in out  # ❌ JSON-escaped


def test_classify_signal_error_detects_compatibility(tmp_env):
    bot = importlib.import_module('bot')
    importlib.reload(bot)

    is_account_fatal, is_compat_issue = bot._classify_signal_error(
        "java.lang.NoSuchMethodError: something changed"
    )
    assert not is_account_fatal
    assert is_compat_issue


def test_monitor_stderr_logs_update_guidance_once_per_cycle(tmp_env, monkeypatch):
    bot = importlib.import_module('bot')
    importlib.reload(bot)

    bot.shutdown_event = threading.Event()
    daemon_shutdown = threading.Event()

    class FakeProc:
        stderr = [
            "java.lang.NoSuchMethodError: foo\n",
            "Unknown version response\n",
        ]

    called = {"count": 0}
    monkeypatch.setattr(bot, "_log_signal_cli_update_guidance", lambda: called.__setitem__("count", called["count"] + 1))

    bot.monitor_stderr(FakeProc(), daemon_shutdown)
    assert called["count"] == 1
    assert daemon_shutdown.is_set()
    assert bot.shutdown_event.is_set()
