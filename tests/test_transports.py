"""Tests for transports.py: YankRequest, SignalReplyContext, RocketChatReplyContext."""
import importlib
import json

import pytest

from transports import YankRequest, SignalReplyContext, RocketChatReplyContext


def test_yank_request_field_shape():
    ctx = object()
    req = YankRequest(url="https://x.com", user_id="u", batch_id=None, reply_context=ctx)
    assert req.url == "https://x.com"
    assert req.user_id == "u"
    assert req.batch_id is None
    assert req.reply_context is ctx


def test_signal_reply_context_send_writes_json_rpc(fake_process, tmp_env):
    ctx = SignalReplyContext(
        process=fake_process,
        group_id="grp",
        recipient_number="+1",
        user_id="uuid-1",
        source_id="+1",
    )
    ctx.send("hello world")
    payload = json.loads(fake_process.stdin.getvalue())
    assert payload.get("method") == "send"
    # message must appear somewhere in the payload
    assert "hello world" in json.dumps(payload)


def test_signal_reply_context_service_is_signal():
    ctx = SignalReplyContext(
        process=None, group_id=None, recipient_number=None,
        user_id="u", source_id="s",
    )
    assert ctx.service == "signal"


def test_signal_reply_context_upload_limit_mb_returns_config_constant(tmp_env):
    import config
    ctx = SignalReplyContext(
        process=None, group_id=None, recipient_number=None,
        user_id="u", source_id="s",
    )
    assert ctx.upload_limit_mb() == config.UPLOAD_LIMIT_MB


def test_rocket_chat_reply_context_send_calls_manager_send():
    calls = []

    class FakeMgr:
        max_upload_mb = 50
        def send(self, room_id, message, attachments=None):
            calls.append((room_id, message, attachments))

    ctx = RocketChatReplyContext(
        manager=FakeMgr(), room_id="rid1", user_id="alice", source_id="uid1",
    )
    ctx.send("test msg", attachments=["/tmp/v.mp4"])

    assert len(calls) == 1
    assert calls[0] == ("rid1", "test msg", ["/tmp/v.mp4"])


def test_rocket_chat_reply_context_service_is_rocketchat():
    ctx = RocketChatReplyContext(
        manager=None, room_id="r", user_id="u", source_id="s",
    )
    assert ctx.service == "rocketchat"


def test_rocket_chat_reply_context_upload_limit_mb_returns_manager_value():
    class FakeMgr:
        max_upload_mb = 75

    ctx = RocketChatReplyContext(
        manager=FakeMgr(), room_id="r", user_id="u", source_id="s",
    )
    assert ctx.upload_limit_mb() == 75
