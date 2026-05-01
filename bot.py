import json
import threading
import time
import os
import sys
import re
import logging
import signal
import random
import subprocess
import queue
import uuid

import video_handler
import signal_manager
import personality
import stats_manager
import datetime
from config import BOT_NUMBER, BOT_UUID, LOGS_DIR
from transports import YankRequest, SignalReplyContext, parse_command

# Ensure logs directory exists
os.makedirs(LOGS_DIR, exist_ok=True)

# Logging Setup
current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = os.path.join(LOGS_DIR, f"alyankovid_{current_time}.log")

# Create a custom handler to force flushing for real-time logging
class FlushFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        FlushFileHandler(log_filename, encoding='utf-8')
    ]
)
logger = logging.getLogger("AlYankoVid")
logger.info(f"Logging to {log_filename}")

# Global shutdown event
shutdown_event = threading.Event()

# Request Queue for Sequential Processing
request_queue = queue.Queue()

# Batch State Tracking: {batch_id: {total, results, reply_context, user_id}}
batch_state = {}
batch_state_lock = threading.Lock()

# --- Exception Handling Hooks ---
def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_uncaught_exception

def handle_thread_exception(args):
    """Capture unhandled exceptions in threads (like subprocess readers)."""
    logger.critical(f"Uncaught exception in thread {args.thread.name}:",
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

threading.excepthook = handle_thread_exception
# -------------------------------

def signal_handler(sig, frame):
    logger.info("Shutdown signal received (Ctrl+C)...")
    shutdown_event.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def worker_thread():
    """Worker thread that processes video requests sequentially."""
    logger.info("Worker thread started, waiting for jobs...")
    while not shutdown_event.is_set():
        try:
            req = request_queue.get(timeout=1.0)
            logger.info(f"Worker picked up job: {req.url} for {req.user_id}")
            handle_video_request(req)
            request_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Worker thread error: {e}", exc_info=True)

def _record_batch_result(batch_id, url, success):
    """Record the result of one URL in a batch and send the summary if all are done."""
    with batch_state_lock:
        state = batch_state.get(batch_id)
        if state is None:
            return
        state['results'].append((url, success))
        if len(state['results']) < state['total']:
            return
        results = state['results']
        reply_context = state['reply_context']
        del batch_state[batch_id]

    header = personality.get_batch_complete()
    lines = [f"{'✅' if ok else '❌'} {u}" for u, ok in results]
    msg = header + "\n" + "\n".join(lines)
    logger.info(f"Batch {batch_id} complete, sending summary.")
    reply_context.send(msg)

def handle_video_request(req):
    """Handles a single video archival request."""
    url = req.url
    user_id = req.user_id
    ctx = req.reply_context
    logger.info(f"Processing request for {url} from {user_id}")
    success = False

    # 1. Acknowledge with a whacky ACK quip
    ctx.send(personality.get_ack())

    # 2. Process
    try:
        def notify_heavy_compression():
            quip = personality.get_heavy_compression_quip()
            logger.info(f"File too large, sending heavy compression notification: {quip}")
            ctx.send(quip)

        def notify_retry():
            msg = "Hmm, that didn't work. Let me update my yt-dlp and try again... 🪗🔧"
            logger.info("Download failed, notifying chat of yt-dlp update retry.")
            ctx.send(msg)

        video_data = video_handler.process_video(
            url, user_id=user_id,
            progress_callback=notify_heavy_compression,
            retry_callback=notify_retry,
            upload_limit_mb=ctx.upload_limit_mb(),
            service=ctx.service,
        )
        video_path, title, description, metadata_path, sub_path, extractor_service, has_audio = video_data

        if video_path and os.path.exists(video_path):
            quip = personality.get_quip()
            msg_parts = [quip]

            if extractor_service == 'TikTok':
                caption = title if title else description
                display_caption = caption.strip() if caption and caption.strip() else "N/A"
                msg_parts.append(f"== Caption ==\n{display_caption}")
            else:
                display_title = title.strip() if title and title.strip() else "N/A"
                display_description = description.strip() if description and description.strip() else "N/A"
                msg_parts.append(f"== Title ==\n{display_title}")
                msg_parts.append(f"== Description ==\n{display_description}")

            if not has_audio:
                msg_parts.append("Accordion autopsy: this version of the video came through without an audio stream, so it'll play silent.")

            final_message = "\n\n".join(msg_parts)

            logger.info(f"Successfully processed {url}, sending structured message.")
            ctx.send(final_message, [video_path])

            # 3. Log Stats
            stats_manager.log_archive(user_id, ctx.source_id, url, video_path,
                                      metadata_path=metadata_path, subtitle_path=sub_path,
                                      service=ctx.service)
            success = True
        else:
            logger.warning(f"Failed to process {url}")
            ctx.send(personality.get_error())
            stats_manager.log_failure(user_id, ctx.source_id, url, "Unknown failure (no video path)",
                                      service=ctx.service)

    except video_handler.FileTooLargeError as e:
        logger.error(str(e))
        ctx.send("This video is too massive for Signal! It's bigger than my Accordion collection!")
        stats_manager.log_failure(user_id, ctx.source_id, url, "File too large", service=ctx.service)
    except video_handler.UnsupportedURLError as e:
        logger.warning(str(e))
        ctx.send(str(e))
        stats_manager.log_failure(user_id, ctx.source_id, url, str(e), service=ctx.service)
    except video_handler.DownloadError as e:
        logger.warning(str(e))
        ctx.send(str(e))
        stats_manager.log_failure(user_id, ctx.source_id, url, str(e), service=ctx.service)
    except Exception as e:
        logger.error(f"Error processing video: {e}", exc_info=True)
        ctx.send(f"Error occurred: {str(e)}")
        stats_manager.log_failure(user_id, ctx.source_id, url, str(e), service=ctx.service)
    finally:
        if req.batch_id is not None:
            _record_batch_result(req.batch_id, url, success)

def process_incoming_message(line, process):
    try:
        msg = json.loads(line)
        if 'method' in msg and msg['method'] == 'receive':
            envelope = msg.get('params', {}).get('envelope', {})
            data_message = envelope.get('dataMessage')

            if data_message:
                message_text = (data_message.get('message') or '').strip()
                source = envelope.get('source')
                if message_text:
                    user_id = source if isinstance(source, str) else (source.get('uuid') or source.get('number') or 'Unknown')
                    source_number = source if isinstance(source, str) else (source.get('number') or source.get('uuid') or 'Unknown')

                    group_info = data_message.get('groupInfo')
                    group_id = group_info.get('groupId') if group_info else None

                    if group_id:
                        logger.info(f"Group message received. mentions={data_message.get('mentions', [])} bodyRanges={data_message.get('bodyRanges', [])} text={message_text[:80]!r}")

                    mentions = data_message.get('mentions', [])
                    body_ranges = data_message.get('bodyRanges', [])
                    is_mentioned = False

                    for mention in mentions:
                        if mention.get('number') == BOT_NUMBER or (BOT_UUID and mention.get('uuid') == BOT_UUID):
                            is_mentioned = True
                            break

                    if not is_mentioned:
                        for r in body_ranges:
                            mention_uuid = r.get('mentionUuid') or r.get('uuid')
                            if mention_uuid == BOT_UUID or r.get('number') == BOT_NUMBER:
                                is_mentioned = True
                                break

                    if not is_mentioned and (mentions or body_ranges):
                        logger.info(f"Unmatched mentions (check BOT_UUID config): mentions={mentions} bodyRanges={body_ranges}")

                    is_dm = group_id is None
                    intent = parse_command(message_text, is_mentioned, is_dm)
                    ctx = SignalReplyContext(
                        process=process,
                        group_id=group_id,
                        recipient_number=source_number,
                        user_id=user_id,
                        source_id=source_number,
                    )

                    if intent[0] == 'delete':
                        url = intent[1]
                        logger.info(f"Processing delete request: {url}")
                        stats_manager.delete_archive(url)
                        ctx.send("Consider it gone! I've scrubbed that video from my digital accordion. 🪗🧹")
                        return

                    if intent[0] == 'yank':
                        urls = intent[1]
                        if len(urls) == 1:
                            logger.info(f"Queuing video request: {urls[0]}")
                            request_queue.put(YankRequest(url=urls[0], user_id=user_id, batch_id=None, reply_context=ctx))
                        else:
                            batch_id = str(uuid.uuid4())
                            with batch_state_lock:
                                batch_state[batch_id] = {
                                    'total': len(urls),
                                    'results': [],
                                    'reply_context': ctx,
                                    'user_id': user_id,
                                }
                            logger.info(f"Queuing batch of {len(urls)} URLs, batch_id={batch_id}")
                            ctx.send(personality.get_batch_ack(len(urls)))
                            for url in urls:
                                logger.info(f"  Queuing batch URL: {url}")
                                request_queue.put(YankRequest(url=url, user_id=user_id, batch_id=batch_id, reply_context=ctx))
                        return

                    if intent[0] == 'stats':
                        stats_msg, top_user = stats_manager.get_formatted_stats()
                        if top_user and top_user == user_id:
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

    except json.JSONDecodeError:
        pass
    except Exception as e:
        logger.error(f"Error processing line: {e}")

FATAL_SIGNAL_ERRORS = [
    "is not registered",
    "Invalid account",
]

SIGNAL_CLI_COMPAT_ERRORS = [
    "Unsupported protocol",
    "Unknown version",
    "NoSuchMethodError",
    "NoSuchFieldError",
    "IncompatibleClassChangeError",
    "Error while parsing incoming websocket message",
    "HTTP 426",
]

def _classify_signal_error(clean_line):
    lower_line = clean_line.lower()
    is_account_fatal = any(err.lower() in lower_line for err in FATAL_SIGNAL_ERRORS)
    is_compat_issue = any(err.lower() in lower_line for err in SIGNAL_CLI_COMPAT_ERRORS)
    return is_account_fatal, is_compat_issue

def _log_signal_cli_update_guidance():
    logger.error("Likely signal-cli compatibility failure detected.")
    logger.error("Refresh the container image to update signal-cli, then recreate the container.")
    logger.error("Suggested commands:")
    logger.error("  docker compose pull")
    logger.error("  docker compose up -d --force-recreate")
    logger.error("If you build locally instead of pulling:")
    logger.error("  docker compose build --no-cache")
    logger.error("  docker compose up -d --force-recreate")

def _log_signal_registration_guidance():
    config_dir = signal_manager.get_last_signal_config_dir() or "/app/data"
    logger.error("Signal account is not registered for configured BOT_NUMBER.")
    logger.error("Run these steps from the unRAID server terminal:")
    logger.error(f"  1) docker exec -it al-yankovid signal-cli --config {config_dir} listAccounts")
    logger.error(f"  2) docker exec -it al-yankovid signal-cli --config {config_dir} -u {BOT_NUMBER} register")
    logger.error(f"  3) docker exec -it al-yankovid signal-cli --config {config_dir} -u {BOT_NUMBER} verify <CODE>")
    logger.error("  4) docker restart al-yankovid")

def monitor_stderr(process, daemon_shutdown):
    """Monitor stderr in a separate thread."""
    update_guidance_logged = False
    registration_guidance_logged = False
    for line in process.stderr:
        if shutdown_event.is_set():
            break
        clean_line = line.strip()
        if clean_line:
            if "INFO" in clean_line:
                logger.info(f"Signal-cli: {clean_line}")
            else:
                logger.warning(f"Signal-cli Stderr: {clean_line}")
                is_account_fatal, is_compat_issue = _classify_signal_error(clean_line)
                if is_compat_issue and not update_guidance_logged:
                    _log_signal_cli_update_guidance()
                    update_guidance_logged = True
                if is_account_fatal and not registration_guidance_logged:
                    _log_signal_registration_guidance()
                    registration_guidance_logged = True
                if is_account_fatal or is_compat_issue:
                    logger.error(f"Fatal signal-cli error — shutting down to prevent restart loop: {clean_line}")
                    daemon_shutdown.set()
                    shutdown_event.set()
                    break

def main():
    import config as _config

    # Worker thread is started once; it no longer holds a reference to the Signal process
    t_worker = threading.Thread(target=worker_thread, daemon=True)
    t_worker.start()

    # Start Rocket.Chat manager if enabled
    rc_manager = None
    if _config.ROCKETCHAT_ENABLED:
        try:
            from rocket_chat_manager import RocketChatManager
            rc_manager = RocketChatManager(
                url=_config.ROCKETCHAT_URL,
                username=_config.ROCKETCHAT_USERNAME,
                password=_config.ROCKETCHAT_PASSWORD,
                bot_username=_config.ROCKETCHAT_BOT_USERNAME,
                request_queue=request_queue,
                shutdown_event=shutdown_event,
                batch_state=batch_state,
                batch_state_lock=batch_state_lock,
            )
            rc_manager.start()
            logger.info("Rocket.Chat manager started.")
        except Exception as e:
            logger.error(f"Rocket.Chat startup failed (Signal-only mode continues): {e}", exc_info=True)
            rc_manager = None

    while not shutdown_event.is_set():
        logger.info("Starting Al YankoVid...")
        process = signal_manager.run_signal_daemon()

        daemon_shutdown = threading.Event()

        def monitor_wrapper(proc, event):
            while not event.is_set() and not shutdown_event.is_set():
                line = proc.stdout.readline()
                if not line:
                    event.set()
                    break
                process_incoming_message(line, proc)

        t_stdout = threading.Thread(target=monitor_wrapper, args=(process, daemon_shutdown), daemon=True)
        t_stderr = threading.Thread(target=monitor_stderr, args=(process, daemon_shutdown), daemon=True)
        t_stdout.start()
        t_stderr.start()

        logger.info("Signal-cli daemon started, waiting for messages...")

        try:
            while not shutdown_event.is_set() and not daemon_shutdown.is_set():
                if process.poll() is not None:
                    logger.error("Signal daemon process terminated.")
                    daemon_shutdown.set()
                    break
                time.sleep(0.1)

        except KeyboardInterrupt:
            shutdown_event.set()
        finally:
            logger.info("Cleaning up Signal daemon...")
            daemon_shutdown.set()
            if process and process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True)
                else:
                    process.terminate()

            if shutdown_event.is_set():
                break
            else:
                logger.info("Daemon crashed or exited. Restarting in 5 seconds...")
                time.sleep(5)

    if rc_manager:
        rc_manager.stop()

    logger.info("Shutdown complete.")

if __name__ == "__main__":
    main()
