"""Tests for RocketChatManager.

All HTTP calls are monkeypatched via requests; WebSocket is replaced by a
FakeWebSocketApp that feeds canned frames synchronously.
"""
import json
import queue
import threading
import importlib
import types

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_login_resp(monkeypatch, rcm_module):
    """Patch requests.post so login succeeds."""
    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"data": {"authToken": "tok123", "userId": "bot_uid"}}

    monkeypatch.setattr(rcm_module.requests, 'post', lambda *a, **k: _Resp())


def _make_settings_resp(monkeypatch, rcm_module, value=104857600):
    """Patch requests.get so /api/v1/settings/FileUpload_MaxFileSize returns value."""
    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"value": value}

    monkeypatch.setattr(rcm_module.requests, 'get', lambda *a, **k: _Resp())


def _build_manager(monkeypatch, rcm_module, tmp_env):
    q = queue.Queue()
    shutdown = threading.Event()
    bs = {}
    bsl = threading.Lock()
    _make_login_resp(monkeypatch, rcm_module)
    _make_settings_resp(monkeypatch, rcm_module)
    mgr = rcm_module.RocketChatManager(
        url="https://chat.example.com",
        username="al-yankovid",
        password="yankyankyank",
        bot_username="al-yankovid",
        request_queue=q,
        shutdown_event=shutdown,
        batch_state=bs,
        batch_state_lock=bsl,
    )
    mgr._login()
    mgr._fetch_max_upload()
    return mgr, q, shutdown


# ---------------------------------------------------------------------------
# Login / auth
# ---------------------------------------------------------------------------

def test_login_success_stores_token_and_user_id(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, _, _ = _build_manager(monkeypatch, rcm, tmp_env)
    assert mgr._auth_token == "tok123"
    assert mgr._user_id == "bot_uid"


def test_login_failure_raises(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)

    class _BadResp:
        status_code = 401
        def raise_for_status(self):
            import requests as r
            raise r.exceptions.HTTPError("401")
        def json(self): return {}

    monkeypatch.setattr(rcm.requests, 'post', lambda *a, **k: _BadResp())
    q = queue.Queue()
    mgr = rcm.RocketChatManager(
        url="https://x.com", username="u", password="p", bot_username="b",
        request_queue=q, shutdown_event=threading.Event(),
        batch_state={}, batch_state_lock=threading.Lock(),
    )
    import requests as rlib
    with pytest.raises(rlib.exceptions.HTTPError):
        mgr._login()


# ---------------------------------------------------------------------------
# Max upload
# ---------------------------------------------------------------------------

def test_fetch_max_upload_returns_mb(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, _, _ = _build_manager(monkeypatch, rcm, tmp_env)
    # 100 MB == 104857600 bytes
    assert mgr.max_upload_mb == 100


def test_fetch_max_upload_falls_back_on_error(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    _make_login_resp(monkeypatch, rcm)

    def _bad_get(*a, **k):
        raise ConnectionError("network down")
    monkeypatch.setattr(rcm.requests, 'get', _bad_get)

    q = queue.Queue()
    mgr = rcm.RocketChatManager(
        url="https://x.com", username="u", password="p", bot_username="b",
        request_queue=q, shutdown_event=threading.Event(),
        batch_state={}, batch_state_lock=threading.Lock(),
    )
    mgr._login()
    mgr._fetch_max_upload()
    assert mgr.max_upload_mb == 100  # fallback


# ---------------------------------------------------------------------------
# Message dispatch helpers
# ---------------------------------------------------------------------------

def _rc_msg(sender_id, sender_username, rid, text, mentions=None, room_type="c"):
    return {
        "u": {"_id": sender_id, "username": sender_username},
        "rid": rid,
        "msg": text,
        "mentions": mentions or [],
        "t": room_type,
    }


# ---------------------------------------------------------------------------
# _on_message routing
# ---------------------------------------------------------------------------

def test_on_message_dm_any_url_queues_yank(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    msg = _rc_msg("uid1", "alice", "DM_rid", "https://youtube.com/v?v=abc", room_type="d")
    mgr._on_message(msg, "DM_rid")

    assert not q.empty()
    req = q.get_nowait()
    assert req.url == "https://youtube.com/v?v=abc"
    assert req.reply_context.service == "rocketchat"


def test_on_message_channel_no_mention_no_keyword_ignored(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    msg = _rc_msg("uid1", "alice", "ch_rid", "https://youtube.com/v?v=abc", room_type="c")
    mgr._on_message(msg, "ch_rid")

    assert q.empty()


def test_on_message_channel_with_mention_queues_yank(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    msg = _rc_msg(
        "uid1", "alice", "ch_rid",
        "@al-yankovid https://youtube.com/v?v=abc",
        mentions=[{"_id": "bot_uid", "username": "al-yankovid"}],
        room_type="c",
    )
    mgr._on_message(msg, "ch_rid")

    assert not q.empty()
    req = q.get_nowait()
    assert req.url.startswith("https://")


def test_on_message_channel_with_yank_keyword_queues_yank(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    msg = _rc_msg("uid1", "alice", "ch_rid", "Yank https://youtube.com/v?v=xyz", room_type="c")
    mgr._on_message(msg, "ch_rid")

    assert not q.empty()


def test_on_message_self_message_ignored(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    # sender_id == bot_uid
    msg = _rc_msg("bot_uid", "al-yankovid", "ch_rid", "Yank https://example.com", room_type="c")
    mgr._on_message(msg, "ch_rid")

    assert q.empty()


def test_on_message_multi_url_queues_batch_with_shared_batch_id(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_batch_ack', lambda n: f'ACK_{n}')

    posted = []
    def fake_post_msg(room_id, text):
        posted.append(text)
    monkeypatch.setattr(mgr, '_post_message', fake_post_msg)

    msg = _rc_msg("uid1", "alice", "DM_rid",
                  "Yank https://a.com https://b.com https://c.com", room_type="d")
    mgr._on_message(msg, "DM_rid")

    assert q.qsize() == 3
    items = [q.get_nowait() for _ in range(3)]
    batch_ids = {i.batch_id for i in items}
    assert len(batch_ids) == 1
    assert list(batch_ids)[0] is not None
    assert any('ACK_3' in p for p in posted)


def test_on_message_stats_invokes_get_formatted_stats_and_sends(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    sm = importlib.import_module('stats_manager')
    monkeypatch.setattr(sm, 'get_formatted_stats', lambda: ('STATS_MSG', None))

    posted = []
    monkeypatch.setattr(mgr, '_post_message', lambda rid, text: posted.append(text))

    msg = _rc_msg("uid1", "alice", "DM_rid", "Al, stats", room_type="d")
    mgr._on_message(msg, "DM_rid")

    assert any('STATS_MSG' in p for p in posted)
    assert q.empty()


def test_on_message_sites_invokes_personality_and_sends(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_sites_quip', lambda: 'SITES_QUIP')

    posted = []
    monkeypatch.setattr(mgr, '_post_message', lambda rid, text: posted.append(text))

    msg = _rc_msg("uid1", "alice", "DM_rid", "Al, sites", room_type="d")
    mgr._on_message(msg, "DM_rid")

    assert 'SITES_QUIP' in posted


def test_on_message_delete_invokes_stats_manager_delete_archive(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    sm = importlib.import_module('stats_manager')
    deleted = []
    monkeypatch.setattr(sm, 'delete_archive', lambda url: deleted.append(url))

    posted = []
    monkeypatch.setattr(mgr, '_post_message', lambda rid, text: posted.append(text))

    msg = _rc_msg("uid1", "alice", "DM_rid", "Al delete https://example.com/v", room_type="d")
    mgr._on_message(msg, "DM_rid")

    assert 'https://example.com/v' in deleted
    assert any('gone' in p.lower() for p in posted)


# ---------------------------------------------------------------------------
# send() / REST helpers
# ---------------------------------------------------------------------------

def test_send_text_calls_chat_postMessage(tmp_env, monkeypatch):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, _, _ = _build_manager(monkeypatch, rcm, tmp_env)

    calls = []

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _Resp()

    monkeypatch.setattr(rcm.requests, 'post', fake_post)

    mgr.send("room123", "hello world")

    assert any("/api/v1/chat.postMessage" in c[0] for c in calls)
    assert any(c[1].get('json', {}).get('roomId') == 'room123' for c in calls)


def test_send_with_attachment_calls_rooms_upload(tmp_env, monkeypatch, tmp_path):
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, _, _ = _build_manager(monkeypatch, rcm, tmp_env)

    video = tmp_path / 'video.mp4'
    video.write_bytes(b'fake video data')

    calls = []

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {}

    def fake_post(url, **kwargs):
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(rcm.requests, 'post', fake_post)

    mgr.send("room123", "check this out", attachments=[str(video)])

    assert any("/api/v1/rooms.upload/room123" in c for c in calls)


# ---------------------------------------------------------------------------
# Reconnect / 401 retry
# ---------------------------------------------------------------------------

def test_reconnect_on_ws_drop_does_not_crash(tmp_env, monkeypatch):
    """_ws_loop should catch exceptions and retry (with backoff)."""
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    _make_login_resp(monkeypatch, rcm)
    _make_settings_resp(monkeypatch, rcm)

    q = queue.Queue()
    shutdown = threading.Event()
    mgr = rcm.RocketChatManager(
        url="https://x.com", username="u", password="p", bot_username="b",
        request_queue=q, shutdown_event=shutdown,
        batch_state={}, batch_state_lock=threading.Lock(),
    )
    mgr._login()

    call_count = [0]

    def fake_run_ws_session():
        call_count[0] += 1
        if call_count[0] < 3:
            raise ConnectionError("simulated drop")
        shutdown.set()  # stop the loop after 3 attempts

    monkeypatch.setattr(mgr, '_run_ws_session', fake_run_ws_session)
    monkeypatch.setattr(shutdown, 'wait', lambda t: None)  # skip actual sleep

    mgr._ws_loop()
    assert call_count[0] == 3


def test_ws_loop_backs_off_on_normal_return(tmp_env, monkeypatch):
    """run_forever() returning normally (no exception) must still apply backoff
    and refresh the auth token — otherwise a down/rejecting server causes a
    zero-delay hot reconnect loop with a stale resume token."""
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    _make_login_resp(monkeypatch, rcm)
    _make_settings_resp(monkeypatch, rcm)

    q = queue.Queue()
    shutdown = threading.Event()
    mgr = rcm.RocketChatManager(
        url="https://x.com", username="u", password="pw", bot_username="b",
        request_queue=q, shutdown_event=shutdown,
        batch_state={}, batch_state_lock=threading.Lock(),
    )
    mgr._login()

    call_count = [0]

    def fake_run_ws_session():
        call_count[0] += 1
        if call_count[0] >= 3:
            shutdown.set()
        return False  # normal return; WS login never succeeded

    monkeypatch.setattr(mgr, '_run_ws_session', fake_run_ws_session)

    relogin = [0]
    monkeypatch.setattr(mgr, '_login', lambda: relogin.__setitem__(0, relogin[0] + 1))

    waits = []
    monkeypatch.setattr(shutdown, 'wait', lambda t: waits.append(t))

    mgr._ws_loop()

    # Backoff delays were applied on normal return (not a zero-delay hot loop)
    assert waits and all(w > 0 for w in waits)
    # Stale resume token refreshed between failed sessions
    assert relogin[0] >= 1


def test_on_message_dm_detected_via_rooms_info_when_t_absent(tmp_env, monkeypatch):
    """Real stream-room-messages payloads omit the room 't' property; the bot
    must resolve it via rooms.info so a bare URL DM still queues a yank."""
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    class _RoomResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"room": {"t": "d"}}

    monkeypatch.setattr(rcm.requests, 'get', lambda *a, **k: _RoomResp())

    msg = {
        "u": {"_id": "uid1", "username": "alice"},
        "rid": "DM_rid",
        "msg": "https://youtube.com/v?v=abc",
        "mentions": [],
        # note: no 't' field, mirroring real RC stream-room-messages frames
    }
    mgr._on_message(msg, "DM_rid")

    assert not q.empty()
    req = q.get_nowait()
    assert req.url == "https://youtube.com/v?v=abc"
    # Resolved room type is cached to avoid a lookup per message
    assert mgr._room_type_cache.get("DM_rid") == "d"


def test_on_message_channel_via_rooms_info_no_keyword_ignored(tmp_env, monkeypatch):
    """A bare URL in a channel (resolved via rooms.info) with no mention/keyword
    stays ignored — DM-implicit-yank must not leak into channels."""
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)
    mgr, q, _ = _build_manager(monkeypatch, rcm, tmp_env)

    class _RoomResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"room": {"t": "c"}}

    monkeypatch.setattr(rcm.requests, 'get', lambda *a, **k: _RoomResp())

    msg = {
        "u": {"_id": "uid1", "username": "alice"},
        "rid": "ch_rid",
        "msg": "https://youtube.com/v?v=abc",
        "mentions": [],
    }
    mgr._on_message(msg, "ch_rid")

    assert q.empty()


def test_401_triggers_relogin_then_retry(tmp_env, monkeypatch):
    """An HTTP 401 on a request causes _login() to be called and the request retried."""
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)

    relogin_count = [0]

    class _GoodResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"data": {"authToken": "new_tok", "userId": "bot_uid"}}

    class _BadResp:
        status_code = 401
        def raise_for_status(self):
            import requests as r
            raise r.exceptions.HTTPError("401")
        def json(self): return {}

    class _OkPostResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {}

    post_calls = [0]

    def fake_post(url, **kwargs):
        if 'login' in url:
            relogin_count[0] += 1
            return _GoodResp()
        post_calls[0] += 1
        # First call returns 401, second returns 200
        if post_calls[0] == 1:
            return _BadResp()
        return _OkPostResp()

    def fake_get(url, **kwargs):
        return type('R', (), {'status_code': 200, 'raise_for_status': lambda s: None, 'json': lambda s: {'value': 104857600}})()

    monkeypatch.setattr(rcm.requests, 'post', fake_post)
    monkeypatch.setattr(rcm.requests, 'get', fake_get)

    q = queue.Queue()
    mgr = rcm.RocketChatManager(
        url="https://x.com", username="u", password="p", bot_username="b",
        request_queue=q, shutdown_event=threading.Event(),
        batch_state={}, batch_state_lock=threading.Lock(),
    )
    mgr._login()
    mgr._fetch_max_upload()

    # _authed_post should catch 401, re-login, and retry
    mgr._post_message("room1", "hello")

    assert relogin_count[0] == 2  # initial login + re-login on 401
    assert post_calls[0] == 2     # 401 attempt + successful retry


# ---------------------------------------------------------------------------
# Service provenance in stats
# ---------------------------------------------------------------------------

def test_yank_via_rc_records_service_rocketchat_in_stats(tmp_env, monkeypatch):
    """handle_video_request called with RocketChatReplyContext records service=rocketchat."""
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    sm = importlib.import_module('stats_manager')
    rcm = importlib.import_module('rocket_chat_manager')
    importlib.reload(rcm)

    import tempfile, os as _os
    tmp = tempfile.mkdtemp()
    v_path = _os.path.join(tmp, 'v.mp4')
    open(v_path, 'wb').write(b'x')

    def fake_pv(url, user_id=None, progress_callback=None, retry_callback=None,
                upload_limit_mb=None, service=None):
        return (v_path, 'T', 'D', None, None, 'YouTube', True)
    monkeypatch.setattr(vh, 'process_video', fake_pv)

    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_ack', lambda: 'ACK')
    monkeypatch.setattr(pers, 'get_quip', lambda: 'QUIP')

    logged = {}
    def fake_log_archive(uid, src_id, url, fp, metadata_path=None, subtitle_path=None, service=None):
        logged['service'] = service
    monkeypatch.setattr(sm, 'log_archive', fake_log_archive)

    class FakeMgr:
        max_upload_mb = 100
        def send(self, room_id, message, attachments=None):
            pass

    from transports import RocketChatReplyContext, YankRequest
    ctx = RocketChatReplyContext(
        manager=FakeMgr(), room_id='rid1', user_id='alice', source_id='uid1',
    )
    req = YankRequest(url='https://yt.be/x', user_id='alice', batch_id=None, reply_context=ctx)
    bot.handle_video_request(req)

    assert logged.get('service') == 'rocketchat'


def test_yank_via_signal_records_service_signal_in_stats(tmp_env, fake_process, monkeypatch, tmp_path):
    """handle_video_request called with SignalReplyContext records service=signal."""
    bot = importlib.import_module('bot')
    importlib.reload(bot)
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)
    sm = importlib.import_module('stats_manager')

    v = tmp_path / 'v.mp4'
    v.write_bytes(b'x')

    def fake_pv(url, user_id=None, progress_callback=None, retry_callback=None,
                upload_limit_mb=None, service=None):
        return (str(v), 'T', 'D', None, None, 'YouTube', True)
    monkeypatch.setattr(vh, 'process_video', fake_pv)

    pers = importlib.import_module('personality')
    monkeypatch.setattr(pers, 'get_ack', lambda: 'ACK')
    monkeypatch.setattr(pers, 'get_quip', lambda: 'QUIP')

    logged = {}
    def fake_log_archive(uid, src_id, url, fp, metadata_path=None, subtitle_path=None, service=None):
        logged['service'] = service
    monkeypatch.setattr(sm, 'log_archive', fake_log_archive)

    from transports import SignalReplyContext, YankRequest
    ctx = SignalReplyContext(
        process=fake_process, group_id=None, recipient_number='+1',
        user_id='u', source_id='+1',
    )
    req = YankRequest(url='https://yt.be/y', user_id='u', batch_id=None, reply_context=ctx)
    bot.handle_video_request(req)

    assert logged.get('service') == 'signal'


def test_legacy_stats_entry_without_service_field_reads_clean(tmp_env):
    """Entries written before this change (no 'service' field) must not error."""
    sm = importlib.import_module('stats_manager')
    importlib.reload(sm)

    # Write a legacy-style entry directly
    stats = {
        "users": {
            "legacy_user": {
                "name": "old user",
                "phone": "+0",
                "archives": [
                    {"url": "https://x.com", "timestamp": "2024-01-01T00:00:00",
                     "filepath": "/archive/x", "metadata_path": None, "subtitle_path": None}
                ],
                "failures": []
            }
        }
    }
    import json, os
    from config import STATS_FILE
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f)

    loaded = sm.load_stats()
    entry = loaded["users"]["legacy_user"]["archives"][0]
    # No KeyError; service field simply absent (legacy)
    assert "service" not in entry
    assert entry["url"] == "https://x.com"
