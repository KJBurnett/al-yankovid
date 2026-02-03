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

import video_handler
import signal_manager
import personality
import stats_manager
import datetime
from config import BOT_NUMBER, LOGS_DIR

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

def worker_thread(process):
    """Worker thread that processes video requests sequentially."""
    logger.info("Worker thread started, waiting for jobs...")
    while not shutdown_event.is_set():
        try:
            # Get request from queue with a timeout to check shutdown flag
            item = request_queue.get(timeout=1.0)
            url, group_id, user_id, source_number = item
            
            logger.info(f"Worker picked up job: {url} for {user_id}")
            handle_video_request(url, group_id, user_id, source_number, process)
            
            request_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Worker thread error: {e}", exc_info=True)

def handle_video_request(url, group_id, user_id, source_number, process):
    """Handles a single video archival request."""
    # Note: user_id should be the UUID for internal/filesystem use, 
    # but we use it for messaging too if it's the only identifier.
    
    # The original `envelope` and `data_message` are now processed in `process_incoming_message`
    # and `group_id` and `user_id` are passed directly.
    
    logger.info(f"Processing request for {url} from {user_id}")
    
    # 1. Acknowledge with a whacky ACK quip
    signal_manager.send_message(process, group_id, user_id, personality.get_ack())
    
    # 2. Process

    try:
        # Define callback for heavy compression notification
        def notify_heavy_compression():
            quip = personality.get_heavy_compression_quip()
            logger.info(f"File too large, sending heavy compression notification: {quip}")
            signal_manager.send_message(process, group_id, user_id, quip)

        video_data = video_handler.process_video(url, user_id=user_id, progress_callback=notify_heavy_compression)
        # video_data now returns: archived_file_path, title, description, metadata_path, sub_path, service
        video_path, title, description, metadata_path, sub_path, service = video_data
        
        if video_path and os.path.exists(video_path):
            # Construct formatted message
            quip = personality.get_quip()
            msg_parts = [quip]
            
            if service == 'TikTok':
                # TikTok only has a caption, so we use one clean header
                caption = title if title else description
                display_caption = caption.strip() if caption and caption.strip() else "N/A"
                msg_parts.append(f"== Caption ==\n{display_caption}")
            else:
                # Other services (YouTube, etc.) have distinct titles and descriptions
                display_title = title.strip() if title and title.strip() else "N/A"
                display_description = description.strip() if description and description.strip() else "N/A"
                msg_parts.append(f"== Title ==\n{display_title}")
                msg_parts.append(f"== Description ==\n{display_description}")
            
            final_message = "\n\n".join(msg_parts)
            
            logger.info(f"Successfully processed {url}, sending structured message.")
            signal_manager.send_message(process, group_id, user_id, final_message, [video_path])
            
            # 3. Log Stats
            stats_manager.log_archive(user_id, source_number, url, video_path, 
                                     metadata_path=metadata_path, subtitle_path=sub_path)
            
        else:
            logger.warning(f"Failed to process {url}")
            signal_manager.send_message(process, group_id, user_id, personality.get_error())
            stats_manager.log_failure(user_id, source_number, url, "Unknown failure (no video path)")
            
    except video_handler.FileTooLargeError as e:
        logger.error(str(e))
        signal_manager.send_message(process, group_id, user_id, "This video is too massive for Signal! It's bigger than my Accordion collection!")
        stats_manager.log_failure(user_id, source_number, url, "File too large")
    except video_handler.UnsupportedURLError as e:
        logger.warning(str(e))
        signal_manager.send_message(process, group_id, user_id, str(e))
        stats_manager.log_failure(user_id, source_number, url, str(e))
    except video_handler.DownloadError as e:
        logger.warning(str(e))
        signal_manager.send_message(process, group_id, user_id, str(e))
        stats_manager.log_failure(user_id, source_number, url, str(e))
    except Exception as e:
        logger.error(f"Error processing video: {e}", exc_info=True)
        signal_manager.send_message(process, group_id, user_id, f"Error occurred: {str(e)}")
        stats_manager.log_failure(user_id, source_number, url, str(e))

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
                    # Prefer UUID for identifying folders/stats
                    user_id = source if isinstance(source, str) else (source.get('uuid') or source.get('number') or 'Unknown')
                    source_number = source if isinstance(source, str) else (source.get('number') or source.get('uuid') or 'Unknown')
                    
                    group_info = data_message.get('groupInfo')
                    group_id = group_info.get('groupId') if group_info else None
                    
                    # 1. Check for @mentions of Al in groups

                    mentions = data_message.get('mentions', [])
                    is_mentioned = False
                    for mention in mentions:
                        if mention.get('number') == BOT_NUMBER:
                            is_mentioned = True
                            break
                    
                    # 2. Check for "Yank {url}" OR (mentioned AND contains URL)
                    url_match = re.search(r'(https?://\S+)', message_text)
                    yank_match = re.search(r'Yank\s+(https?://\S+)', message_text, re.IGNORECASE)
                    
                    if yank_match:
                        url = yank_match.group(1)
                        logger.info(f"Queuing video request: {url}")
                        request_queue.put((url, group_id, user_id, source_number))
                        return
                    elif is_mentioned and url_match:
                        # Check if it's a delete command first
                        delete_match = re.search(r'delete\s+(https?://\S+)', message_text, re.IGNORECASE)
                        if delete_match:
                            url = delete_match.group(1)
                            logger.info(f"Processing delete request: {url}")
                            stats_manager.delete_archive(url)
                            signal_manager.send_message(process, group_id, user_id, f"Consider it gone! I've scrubbed that video from my digital accordion. 🪗🧹")
                            return
                        
                        url = url_match.group(1)
                        logger.info(f"Queuing video request: {url}")
                        request_queue.put((url, group_id, user_id, source_number))
                        return

                    # 3. Check for "stats" command
                    if re.search(r'\b(Al,?\s+stats|stats,?\s+Al)\b', message_text, re.IGNORECASE) or \
                       (is_mentioned and re.search(r'\bstats\b', message_text, re.IGNORECASE)):
                        
                        stats_msg, top_user = stats_manager.get_formatted_stats()
                        
                        # Add Top User Quip if applicable
                        if top_user and top_user == user_id:
                            stats_msg += f"\n\n{personality.get_top_user_quip()}"
                            
                        signal_manager.send_message(process, group_id, user_id, stats_msg)
                        return

                    # 4. Check for "how are you" / "what's up"
                    if re.search(r'\bAl,?\s+(how\s+are\s+you|how\'s\s+it\s+going|what\'s\s+up|howdy)\b', message_text, re.IGNORECASE) or \
                       re.search(r'\b(how\s+are\s+you|how\'s\s+it\s+going|what\'s\s+up|howdy),?\s+Al\b', message_text, re.IGNORECASE) or \
                       (is_mentioned and re.search(r'\b(how\s+are\s+you|how\'s\s+it\s+going|what\'s\s+up|howdy)\b', message_text, re.IGNORECASE)):
                        signal_manager.send_message(process, group_id, user_id, personality.get_conversational())
                        return

                    # 5. Check for Greetings
                    if re.search(r'\b(Al,?\s+(hi|hello|hey|yo|howdy)|(hi|hello|hey|yo|howdy)\s+,?Al)\b', message_text, re.IGNORECASE) or \
                       (is_mentioned and re.search(r'\b(hi|hello|hey|yo|howdy)\b', message_text, re.IGNORECASE)):
                        signal_manager.send_message(process, group_id, user_id, personality.get_greeting())
                        return

                    # 6. Check for "sites" command
                    if re.search(r'\b(Al,?\s+sites|sites,?\s+Al)\b', message_text, re.IGNORECASE) or \
                       (is_mentioned and re.search(r'\bsites\b', message_text, re.IGNORECASE)):
                        signal_manager.send_message(process, group_id, user_id, personality.get_sites_quip())
                        return
                        
    except json.JSONDecodeError:
        pass
    except Exception as e:
        logger.error(f"Error processing line: {e}")

def monitor_stderr(process):
    """Monitor stderr in a separate thread."""
    for line in process.stderr:
        if shutdown_event.is_set():
            break
        clean_line = line.strip()
        if clean_line:
            # Check for benign info messages from signal-cli that might appear in stderr
            if "INFO" in clean_line:
                logger.info(f"Signal-cli: {clean_line}")
            else:
                logger.warning(f"Signal-cli Stderr: {clean_line}")

def main():
    while not shutdown_event.is_set():
        logger.info("Starting Al YankoVid...")
        process = signal_manager.run_signal_daemon()
        
        daemon_shutdown = threading.Event()
        
        # Start the worker thread for sequential video processing
        # We start it once per daemon run (or could be global, but passing 'process' is needed)
        # Actually better to make it global or passed in, but 'process' changes on restart.
        # So we start a new worker each time we start the daemon, and ensure the old one dies?
        # The 'process' arg in worker_thread is the ONLY thing determining where it sends.
        # So yes, start a new worker thread.
        
        t_worker = threading.Thread(target=worker_thread, args=(process,), daemon=True)
        t_worker.start()

        def monitor_wrapper(proc, event):
            while not event.is_set() and not shutdown_event.is_set():
                line = proc.stdout.readline()
                if not line:
                    event.set()
                    break
                process_incoming_message(line, proc)

        t_stdout = threading.Thread(target=monitor_wrapper, args=(process, daemon_shutdown), daemon=True)
        t_stderr = threading.Thread(target=monitor_stderr, args=(process,), daemon=True)
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

    logger.info("Shutdown complete.")

if __name__ == "__main__":
    main()
