import json
import logging
import threading
import time
import uuid
import os

import requests

import personality
import stats_manager
from transports import YankRequest, RocketChatReplyContext, parse_command

logger = logging.getLogger("AlYankoVid.RocketChat")


class RocketChatManager:
    def __init__(self, url, username, password, bot_username,
                 request_queue, shutdown_event, batch_state, batch_state_lock):
        self._base_url = url.rstrip('/')
        self._username = username
        self._password = password
        self.bot_username = bot_username
        self._request_queue = request_queue
        self._shutdown_event = shutdown_event
        self._batch_state = batch_state
        self._batch_state_lock = batch_state_lock

        self._auth_token = None
        self._user_id = None   # RC immutable _id of the bot account
        self.max_upload_mb = 100

        self._thread = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        self._login()
        self._fetch_max_upload()
        self._thread = threading.Thread(target=self._ws_loop, daemon=True, name="rc-ws-loop")
        self._thread.start()

    def stop(self):
        # WebSocket loop exits when _shutdown_event is set; nothing extra needed.
        pass

    def send(self, room_id, message, attachments=None):
        if attachments:
            self._upload_file(room_id, attachments[0], msg=message)
        else:
            self._post_message(room_id, message)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _login(self):
        resp = requests.post(
            f"{self._base_url}/api/v1/login",
            json={"user": self._username, "password": self._password},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        self._auth_token = data["authToken"]
        self._user_id = data["userId"]
        logger.info(f"Rocket.Chat login OK (userId={self._user_id})")

    def _headers(self):
        return {
            "X-Auth-Token": self._auth_token,
            "X-User-Id": self._user_id,
        }

    def _authed_get(self, path, **kwargs):
        resp = requests.get(f"{self._base_url}{path}", headers=self._headers(), timeout=15, **kwargs)
        if resp.status_code == 401:
            logger.warning("RC 401 — re-logging in and retrying GET")
            self._login()
            resp = requests.get(f"{self._base_url}{path}", headers=self._headers(), timeout=15, **kwargs)
        resp.raise_for_status()
        return resp

    def _authed_post(self, path, **kwargs):
        resp = requests.post(f"{self._base_url}{path}", headers=self._headers(), timeout=30, **kwargs)
        if resp.status_code == 401:
            logger.warning("RC 401 — re-logging in and retrying POST")
            self._login()
            resp = requests.post(f"{self._base_url}{path}", headers=self._headers(), timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Settings / config
    # ------------------------------------------------------------------

    def _fetch_max_upload(self):
        try:
            resp = self._authed_get("/api/v1/settings/FileUpload_MaxFileSize")
            value = resp.json().get("value")
            if value and int(value) > 0:
                self.max_upload_mb = int(int(value) / (1024 * 1024))
                logger.info(f"Max upload size from RC: {self.max_upload_mb} MB")
            else:
                logger.info("RC max upload size null/zero — using fallback 100 MB")
        except Exception as e:
            logger.warning(f"Could not fetch RC FileUpload_MaxFileSize: {e} — using fallback 100 MB")

    # ------------------------------------------------------------------
    # WebSocket / DDP loop
    # ------------------------------------------------------------------

    def _ws_loop(self):
        attempt = 0
        while not self._shutdown_event.is_set():
            try:
                self._run_ws_session()
                attempt = 0
            except Exception as e:
                if self._shutdown_event.is_set():
                    break
                delay = min(60, 2 ** attempt)
                logger.warning(f"RC WebSocket error: {e}. Reconnecting in {delay}s (attempt {attempt})")
                attempt += 1
                self._shutdown_event.wait(delay)

    def _run_ws_session(self):
        import websocket  # websocket-client

        ws_url = self._base_url.replace("https://", "wss://").replace("http://", "ws://") + "/websocket"
        logger.info(f"Connecting RC WebSocket: {ws_url}")

        connected_event = threading.Event()
        login_event = threading.Event()
        sub_id = str(uuid.uuid4())[:8]
        login_id = str(uuid.uuid4())[:8]
        connect_id = str(uuid.uuid4())[:8]
        msg_counter = [0]

        def _send(ws, payload):
            ws.send(json.dumps(payload))

        def on_open(ws):
            _send(ws, {"msg": "connect", "version": "1", "support": ["1", "pre2", "pre1"]})

        def on_message(ws, raw):
            try:
                msg = json.loads(raw)
            except Exception:
                return

            kind = msg.get("msg")

            if kind == "connected":
                connected_event.set()
                _send(ws, {
                    "msg": "method",
                    "method": "login",
                    "id": login_id,
                    "params": [{"resume": self._auth_token}],
                })
                return

            if kind == "result" and msg.get("id") == login_id:
                if "error" in msg:
                    logger.error(f"RC WS login failed: {msg['error']}")
                    ws.close()
                    return
                login_event.set()
                _send(ws, {
                    "msg": "sub",
                    "id": sub_id,
                    "name": "stream-room-messages",
                    "params": ["__my_messages__", False],
                })
                return

            if kind == "ping":
                _send(ws, {"msg": "pong"})
                return

            if kind == "changed" and msg.get("collection") == "stream-room-messages":
                try:
                    fields = msg.get("fields", {})
                    args = fields.get("args", [])
                    if args:
                        room_type = fields.get("eventName", "")
                        self._on_message(args[0], room_type)
                except Exception as e:
                    logger.error(f"RC _on_message error: {e}", exc_info=True)

        def on_error(ws, error):
            logger.warning(f"RC WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            logger.info(f"RC WebSocket closed: {close_status_code} {close_msg}")

        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        ping_stop = threading.Event()

        def _keepalive():
            while not ping_stop.is_set() and not self._shutdown_event.is_set():
                ping_stop.wait(25)
                if not ping_stop.is_set():
                    try:
                        ws.send(json.dumps({"msg": "ping"}))
                    except Exception:
                        break

        ping_thread = threading.Thread(target=_keepalive, daemon=True)
        ping_thread.start()

        try:
            ws.run_forever()
        finally:
            ping_stop.set()

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def _on_message(self, rc_msg, event_name):
        sender_id = rc_msg.get("u", {}).get("_id", "")
        sender_username = rc_msg.get("u", {}).get("username", "")

        # Ignore own messages and edits by self
        if sender_id == self._user_id:
            return
        if rc_msg.get("editedBy", {}).get("_id") == self._user_id:
            return

        rid = rc_msg.get("rid", "")
        text = (rc_msg.get("msg") or "").strip()
        if not text:
            return

        # Determine room type: 'd' = DM, 'c' = channel, 'p' = private group
        # The eventName in __my_messages__ is the room_id, so we fall back to t field
        room_type = rc_msg.get("t") or rc_msg.get("roomType", "")
        # Try to get from the subscription args[1] if available (not always present)
        is_dm = room_type == "d"

        # Mention detection
        mentions = rc_msg.get("mentions") or []
        is_mentioned = any(
            m.get("_id") == self._user_id or m.get("username") == self.bot_username
            for m in mentions
        )

        logger.info(f"RC message from {sender_username} in {rid} (dm={is_dm}, mentioned={is_mentioned}): {text[:80]!r}")

        ctx = RocketChatReplyContext(
            manager=self,
            room_id=rid,
            user_id=sender_username,
            source_id=sender_id,
        )

        intent = parse_command(text, is_mentioned, is_dm)

        if intent[0] == 'ignore':
            return

        if intent[0] == 'delete':
            url = intent[1]
            logger.info(f"RC delete request: {url}")
            stats_manager.delete_archive(url)
            ctx.send("Consider it gone! I've scrubbed that video from my digital accordion. 🪗🧹")
            return

        if intent[0] == 'yank':
            urls = intent[1]
            if len(urls) == 1:
                logger.info(f"RC queuing: {urls[0]}")
                self._request_queue.put(YankRequest(url=urls[0], user_id=sender_username, batch_id=None, reply_context=ctx))
            else:
                batch_id = str(uuid.uuid4())
                with self._batch_state_lock:
                    self._batch_state[batch_id] = {
                        'total': len(urls),
                        'results': [],
                        'reply_context': ctx,
                        'user_id': sender_username,
                    }
                logger.info(f"RC queuing batch of {len(urls)}, batch_id={batch_id}")
                ctx.send(personality.get_batch_ack(len(urls)))
                for url in urls:
                    self._request_queue.put(YankRequest(url=url, user_id=sender_username, batch_id=batch_id, reply_context=ctx))
            return

        if intent[0] == 'stats':
            stats_msg, top_user = stats_manager.get_formatted_stats()
            if top_user and top_user == sender_username:
                stats_msg += f"\n\n{personality.get_top_user_quip()}"
            ctx.send(stats_msg)
            return

        if intent[0] == 'conversational':
            ctx.send(personality.get_conversational())
            return

        if intent[0] == 'greeting':
            ctx.send(personality.get_greeting())
            return

        if intent[0] == 'sites':
            ctx.send(personality.get_sites_quip())
            return

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    def _post_message(self, room_id, text):
        chunks = self._chunk_text(text)
        for chunk in chunks:
            self._authed_post("/api/v1/chat.postMessage", json={"roomId": room_id, "text": chunk})

    def _upload_file(self, room_id, file_path, msg=None):
        with open(file_path, 'rb') as f:
            filename = os.path.basename(file_path)
            files = {"file": (filename, f)}
            data = {}
            if msg:
                data["msg"] = msg
            self._authed_post(f"/api/v1/rooms.upload/{room_id}", files=files, data=data)

    @staticmethod
    def _chunk_text(text, max_len=5000):
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            split = text.rfind('\n\n', 0, max_len)
            if split == -1:
                split = max_len
            chunks.append(text[:split])
            text = text[split:].lstrip('\n')
        return chunks
