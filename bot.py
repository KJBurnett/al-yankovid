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

import video_handler
import signal_manager
import personality
from config import BOT_NUMBER

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AlYankoVid")

# Global shutdown event
shutdown_event = threading.Event()

def signal_handler(sig, frame):
    logger.info("Shutdown signal received (Ctrl+C)...")
    shutdown_event.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def handle_video_request(url, envelope, process):
    """Threaded handler for video requests."""
    source = envelope.get('source')
    source_number = source if isinstance(source, str) else source.get('number', 'Unknown')
    
    data_message = envelope.get('dataMessage')
    group_info = data_message.get('groupInfo') 
    group_id = group_info.get('groupId') if group_info else None
    
    logger.info(f"Processing request for {url} from {source_number}")
    
    # 1. Acknowledge with a whacky ACK quip
    signal_manager.send_message(process, group_id, source_number, personality.get_ack())
    
    # 2. Process
    try:
        video_path = video_handler.process_video(url)
        
        if video_path and os.path.exists(video_path):
            quip = personality.get_quip()
            logger.info(f"Successfully processed {url}, sending with quip: {quip}")
            signal_manager.send_message(process, group_id, source_number, quip, [video_path])
        else:
            logger.warning(f"Failed to process {url}")
            signal_manager.send_message(process, group_id, source_number, personality.get_error())
            
    except video_handler.UnsupportedURLError as e:
        logger.warning(str(e))
        signal_manager.send_message(process, group_id, source_number, str(e))
    except video_handler.DownloadError as e:
        logger.warning(str(e))
        signal_manager.send_message(process, group_id, source_number, str(e))
    except Exception as e:
        logger.error(f"Error processing video: {e}", exc_info=True)
        signal_manager.send_message(process, group_id, source_number, f"Error occurred: {str(e)}")

def process_incoming_message(line, process):
    try:
        msg = json.loads(line)
        if 'method' in msg and msg['method'] == 'receive':
            envelope = msg.get('params', {}).get('envelope', {})
            data_message = envelope.get('dataMessage')
            
            if data_message:
                message_text = (data_message.get('message') or '').strip()
                source = envelope.get('source')
                source_number = source if isinstance(source, str) else source.get('number', 'Unknown')
                group_info = data_message.get('groupInfo')
                group_id = group_info.get('groupId') if group_info else None
                
                if message_text:
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
                        threading.Thread(target=handle_video_request, args=(url, envelope, process), daemon=True).start()
                        return
                    elif is_mentioned and url_match:
                        url = url_match.group(1)
                        threading.Thread(target=handle_video_request, args=(url, envelope, process), daemon=True).start()
                        return

                    # 3. Check for "how are you" / "what's up"
                    if re.search(r'\bAl,?\s+(how\s+are\s+you|how\'s\s+it\s+going|what\'s\s+up|howdy)\b', message_text, re.IGNORECASE) or \
                       re.search(r'\b(how\s+are\s+you|how\'s\s+it\s+going|what\'s\s+up|howdy),?\s+Al\b', message_text, re.IGNORECASE) or \
                       (is_mentioned and re.search(r'\b(how\s+are\s+you|how\'s\s+it\s+going|what\'s\s+up|howdy)\b', message_text, re.IGNORECASE)):
                        signal_manager.send_message(process, group_id, source_number, personality.get_conversational())
                        return

                    # 4. Check for Greetings
                    if re.search(r'\b(Al,?\s+(hi|hello|hey|yo|howdy)|(hi|hello|hey|yo|howdy)\s+,?Al)\b', message_text, re.IGNORECASE) or \
                       (is_mentioned and re.search(r'\b(hi|hello|hey|yo|howdy)\b', message_text, re.IGNORECASE)):
                        signal_manager.send_message(process, group_id, source_number, personality.get_greeting())
                        return

                    # 5. Check for "sites" command
                    if re.search(r'\b(Al,?\s+sites|sites,?\s+Al)\b', message_text, re.IGNORECASE) or \
                       (is_mentioned and re.search(r'\bsites\b', message_text, re.IGNORECASE)):
                        signal_manager.send_message(process, group_id, source_number, personality.get_sites_quip())
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
            logger.warning(f"Signal-cli Stderr: {clean_line}")

def main():
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
