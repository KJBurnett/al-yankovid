import os
import subprocess
import json
import re
import datetime
import shutil
import sys
import logging
import time
from config import ARCHIVE_ROOT, MAX_SIZE_MB, UPLOAD_LIMIT_MB

class FileTooLargeError(Exception):
    """Raised when the final file size exceeds the upload limit."""
    pass

class VideoHandlerError(Exception):
    """Base class for video handler errors."""
    pass

class UnsupportedURLError(VideoHandlerError):
    """Raised when the URL is not supported by yt-dlp."""
    pass

class DownloadError(VideoHandlerError):
    """Raised when a download fails."""
    pass

# Configuration
YT_DLP_CMD = os.path.join(sys.prefix, 'Scripts', 'yt-dlp.exe')
FFMPEG_CMD = 'ffmpeg'

logger = logging.getLogger("AlYankoVid.VideoHandler")

def check_dependencies():
    """Checks if required tools are installed."""
    missing = []
    
    # Check yt-dlp
    if not os.path.exists(YT_DLP_CMD):
        # Try just 'yt-dlp' if the venv path fails
        try:
            subprocess.run(['yt-dlp', '--version'], capture_output=True, check=True, encoding='utf-8')
            globals()['YT_DLP_CMD'] = 'yt-dlp'
        except:
            missing.append("yt-dlp")
            
    # Check ffmpeg
    try:
        subprocess.run([FFMPEG_CMD, '-version'], capture_output=True, check=True, encoding='utf-8')
    except:
        missing.append("ffmpeg")
        
    if missing:
        raise RuntimeError(f"Missing required dependencies: {', '.join(missing)}")
    
    logger.info("Dependencies verified: yt-dlp, ffmpeg")

def clean_filename(title):
    return re.sub(r'[\\/*?:"<>|]', "", title)

def get_video_info(url):
    """Retrieves video metadata using yt-dlp."""
    try:
        command = [YT_DLP_CMD, '-J', url]
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        if "Unsupported URL" in stderr:
            raise UnsupportedURLError("Al says: That URL is as unsupported as an accordion in a library!")
        elif "Authentication is required" in stderr or "sign in" in stderr.lower() or "cookies" in stderr.lower():
            raise DownloadError(f"Error: This video requires a logged in account. You can feed me, the wonderful Yankovid, cookies by looking at https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp")
        else:
            logger.error(f"Error getting video info: {stderr}")
            raise DownloadError(f"Something went wrong while I was scoping out the video: {stderr.split(':')[-1].strip()}")

def download_video(url, output_dir):
    """Downloads video using yt-dlp."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Template: Title [id].ext
    output_template = os.path.join(output_dir, '%(title)s [%(id)s].%(ext)s')
    
    try:
        # Download format: best video+audio that is mp4 compatible or anything else we can merge
        # + Subtitles (English preferred, but any will do)
        command = [
            YT_DLP_CMD, 
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 
            '-o', output_template, 
            '--merge-output-format', 'mp4',
            '--write-subs', '--write-auto-subs', '--sub-langs', 'en,.*',
            url
        ]
        # Capture and log output for deep debugging
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        logger.info(f"yt-dlp output:\n{result.stdout}")
        
        # Find the downloaded file
        info = get_video_info(url)
        if info:
            video_id = info.get('id')
            # Simple search for the file with the ID in the name in the output dir
            video_path = None
            for file in os.listdir(output_dir):
                if video_id in file and file.endswith('.mp4'):
                    video_path = os.path.join(output_dir, file)
                    break
            return video_path
        return None
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        logger.error(f"Error downloading video: {stderr}")
        raise DownloadError(f"The download failed! My digital bellows popped: {stderr.split(':')[-1].strip()}")
    except VideoHandlerError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during download: {e}")
        raise DownloadError(f"Even I don't know what happened there! *Accordion screech*")

def archive_metadata(archive_dir, info):
    """Saves relevant metadata to a JSON file in the archive."""
    metadata = {
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "uploader": info.get("uploader", ""),
        "timestamp": info.get("timestamp") or datetime.datetime.now().isoformat(),
        "original_url": info.get("original_url", info.get("webpage_url", ""))
    }
    metadata_path = os.path.join(archive_dir, "metadata.json")
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
    return metadata_path

def get_file_size_mb(path):
    return os.path.getsize(path) / (1024 * 1024)

def load_archive_index():
    index_path = os.path.join(ARCHIVE_ROOT, 'index.json')
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r') as f:
                return json.load(f)
        except:
            logger.warning("Archive index corrupted, starting fresh.")
            return {}
    return {}

def save_archive_index(index):
    if not os.path.exists(ARCHIVE_ROOT):
        os.makedirs(ARCHIVE_ROOT)
    index_path = os.path.join(ARCHIVE_ROOT, 'index.json')
    with open(index_path, 'w') as f:
        json.dump(index, f, indent=4)

def check_archive(url):
    """Checks if the URL has already been downloaded."""
    index = load_archive_index()
    return index.get(url)

def compress_video(input_path, target_size_mb, force_normalize=True):
    """Compresses or normalizes video for iOS compatibility."""
    file_size = get_file_size_mb(input_path)
    
    # We always want to normalize for iOS compatibility (faststart + yuv420p)
    # unless it's already a result of our own processing.
    if not force_normalize and file_size <= target_size_mb:
        return input_path

    logger.info(f"Processing {input_path} ({file_size:.2f} MB) for iOS/Signal compatibility")
    
    output_path = os.path.splitext(input_path)[0] + "_normalized.mp4"
    temp_dir = os.path.dirname(input_path)
    pass_log_prefix = os.path.join(temp_dir, f"ffmpeg2pass_{os.getpid()}")
    
    # Retry mechanism for compression (handles transient 'rename' file locking errors on Windows)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Get duration and bitrate
            probe = subprocess.run([
                'ffprobe', '-v', 'error', 
                '-show_entries', 'format=duration:format=bit_rate', 
                '-of', 'default=noprint_wrappers=1:nokey=1', 
                input_path
            ], capture_output=True, text=True, check=True, encoding='utf-8')
            
            # Output might be multiline, e.g. duration\nbit_rate
            probe_output = probe.stdout.strip().split()
            if len(probe_output) >= 1:
                duration = float(probe_output[0])
                # Default to high bitrate if unknown, so we use target based calc
                original_bitrate = float(probe_output[1]) if len(probe_output) > 1 and probe_output[1] != 'N/A' else 50000000 
            else:
                 # Fallback
                duration = 60
                original_bitrate = 50000000

            # Target bitrate = target size / duration
            target_total_bitrate = (target_size_mb * 8 * 1024 * 1024) / duration
            
            # Smart Compression: Don't exceed original bitrate if file is small
            if file_size < target_size_mb:
                 target_total_bitrate = min(target_total_bitrate, original_bitrate)

            audio_bitrate = 128 * 1024
            video_bitrate = max(target_total_bitrate - audio_bitrate, 100 * 1024) # Min 100k
            
            # Pass 1
            dev_null = 'NUL' if os.name == 'nt' else '/dev/null'
            command = [
                FFMPEG_CMD, '-y',
                '-i', input_path,
                '-c:v', 'libx264',
                '-b:v', str(int(video_bitrate)),
                '-pass', '1',
                '-passlogfile', pass_log_prefix,
                '-f', 'mp4',
                '-movflags', '+faststart',
                '-pix_fmt', 'yuv420p',
                dev_null
            ]
            # Use run but handle errors manually to allow retrying
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, command, output=result.stdout, stderr=result.stderr)
            
            # Pass 2
            command = [
                FFMPEG_CMD, '-y',
                '-i', input_path,
                '-c:v', 'libx264',
                '-b:v', str(int(video_bitrate)),
                '-pass', '2',
                '-passlogfile', pass_log_prefix,
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',
                '-pix_fmt', 'yuv420p',
                output_path
            ]
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
            if result.returncode != 0:
                 raise subprocess.CalledProcessError(result.returncode, command, output=result.stdout, stderr=result.stderr)
            
            # Cleanup pass logs
            for f in os.listdir(temp_dir):
                if f.startswith(os.path.basename(pass_log_prefix)):
                    try: os.remove(os.path.join(temp_dir, f))
                    except: pass
            
            return output_path

        except Exception as e:
            logger.warning(f"Compression attempt {attempt+1}/{max_retries} failed: {e}")
            if hasattr(e, 'stderr'):
                logger.warning(f"FFmpeg Stderr: {e.stderr}")
            if attempt < max_retries - 1:
                time.sleep(2) # Wait a bit before retrying (let file locks release)
            else:
                logger.error(f"Normalization/Compression failed after {max_retries} attempts.")
                # Return original input path on final failure
                return input_path

def find_subtitle_file(directory, video_filename_base):
    """Finds the best subtitle file matching the video base name."""
    candidates = []
    video_base = os.path.splitext(video_filename_base)[0]
    
    for f in os.listdir(directory):
        if f.startswith(video_base) and f.endswith(('.vtt', '.srt', '.ass')):
             candidates.append(f)
    
    if not candidates:
        return None
        
    # Priority: English (.en.), then first available
    selected = None
    for c in candidates:
        if '.en.' in c:
            selected = c
            break
    
    if not selected:
        selected = candidates[0]
        
    return os.path.join(directory, selected)

def update_ytdlp():
    """Attempts to update yt-dlp to the latest version."""
    logger.info("Attempting to update yt-dlp...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-U', 'yt-dlp'], check=True, capture_output=True, encoding='utf-8')
        logger.info("yt-dlp updated successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to update yt-dlp: {e}")
        return False

def process_video(url, user_id="Unknown", retry=True, progress_callback=None):
    """Main workflow for a video URL. Returns (file_path, title, description, metadata_path, sub_path)."""
    # 1. Check Archive
    archived_path = check_archive(url)
    if archived_path and os.path.exists(archived_path):
        logger.info(f"Found in archive: {archived_path}")
        # Try to find metadata.json and subtitles in the same directory
        archive_dir = os.path.dirname(archived_path)
        metadata_path = os.path.join(archive_dir, "metadata.json")
        title, description = "", ""
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    title = meta.get("title", "")
                    description = meta.get("description", "")
            except: pass
            
        sub_path = find_subtitle_file(archive_dir, os.path.basename(archived_path))
        return archived_path, title, description, (metadata_path if os.path.exists(metadata_path) else None), sub_path

    # Unique temp dir for concurrency
    import uuid
    temp_dir = os.path.join(os.getcwd(), f'temp_download_{uuid.uuid4().hex}')
    try:
        # 2. Extract Info
        info = get_video_info(url)
        title = info.get("title", "")
        description = info.get("description", "")

        # 3. Download
        try:
            downloaded_path = download_video(url, temp_dir)
        except DownloadError as e:
            if retry:
                logger.warning(f"Download failed: {e}. Attempting yt-dlp update and retry...")
                update_ytdlp()
                time.sleep(2)
                return process_video(url, user_id=user_id, retry=False, progress_callback=progress_callback)
            else:
                raise

        if not downloaded_path:
            return None, None, None, None, None

        # 4. Normalize/Compress
        final_path = compress_video(downloaded_path, MAX_SIZE_MB, force_normalize=True)

        # 4.5. Oversized File Guard
        final_size = get_file_size_mb(final_path)
        if final_size > UPLOAD_LIMIT_MB:
            if progress_callback:
                progress_callback()
            logger.info(f"Attempting aggressive compression for {final_size:.2f}MB video...")
            aggressive_path = compress_video(final_path, MAX_SIZE_MB * 0.85, force_normalize=True)
            final_path = aggressive_path
            final_size = get_file_size_mb(final_path)
            if final_size > UPLOAD_LIMIT_MB:
                 raise FileTooLargeError(f"Video still too large ({final_size:.2f}MB) after aggressive compression.")

        # 5. Archive
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        archive_dir = os.path.join(ARCHIVE_ROOT, str(user_id), timestamp)
        os.makedirs(archive_dir, exist_ok=True)
        
        # Save Metadata
        metadata_path = archive_metadata(archive_dir, info)
        
        filename = os.path.basename(final_path)
        archived_file_path = os.path.join(archive_dir, filename)
        shutil.move(final_path, archived_file_path)

        # 6. Handle Subtitles
        download_filename = os.path.basename(downloaded_path)
        selected_sub = find_subtitle_file(temp_dir, download_filename)
        archived_sub_path = None
        if selected_sub:
            sub_ext = os.path.splitext(selected_sub)[1]
            video_base = os.path.splitext(filename)[0]
            new_sub_name = video_base + sub_ext
            archived_sub_path = os.path.join(archive_dir, new_sub_name)
            shutil.move(selected_sub, archived_sub_path)
            logger.info(f"Archived subtitle: {archived_sub_path}")
        
        # Update index
        index = load_archive_index()
        index[url] = archived_file_path
        save_archive_index(index)
        
        return archived_file_path, title, description, metadata_path, archived_sub_path

    except Exception as e:
        logger.error(f"Failed to process video {url}: {e}", exc_info=True)
        raise
    finally:
        if os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except: pass

# Verify dependencies on module load
try:
    check_dependencies()
except Exception as e:
    logger.error(f"CRITICAL ERROR: {e}")
