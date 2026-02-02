import os
import subprocess
import json
import re
import datetime
import shutil
import sys
import logging
from config import ARCHIVE_ROOT, MAX_SIZE_MB

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
YT_DLP_CMD = [sys.executable, '-m', 'yt_dlp']
FFMPEG_CMD = 'ffmpeg'

logger = logging.getLogger("AlYankoVid.VideoHandler")

def check_dependencies():
    """Checks if required tools are installed."""
    missing = []
    
    # Check yt-dlp
    try:
        subprocess.run([*YT_DLP_CMD, '--version'], capture_output=True, check=True)
    except:
        # Fallback to system yt-dlp
        try:
            subprocess.run(['yt-dlp', '--version'], capture_output=True, check=True)
            globals()['YT_DLP_CMD'] = ['yt-dlp']
        except:
            missing.append("yt-dlp")
            
    # Check ffmpeg
    try:
        subprocess.run([FFMPEG_CMD, '-version'], capture_output=True, check=True)
    except:
        missing.append("ffmpeg")
        
    if missing:
        raise RuntimeError(f"Missing required dependencies: {', '.join(missing)}")
    
    logger.info(f"Dependencies verified: {YT_DLP_CMD}, ffmpeg")

def clean_filename(title):
    return re.sub(r'[\\/*?:"<>|]', "", title)

def get_video_info(url):
    """Retrieves video metadata using yt-dlp."""
    try:
        command = [*YT_DLP_CMD, '-J', url]
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        stdout = e.stdout or ""
        logger.error(f"Error getting video info:\nStdout: {stdout}\nStderr: {stderr}")
        
        if "Unsupported URL" in stderr:
            raise UnsupportedURLError("Al says: That URL is as unsupported as an accordion in a library!")
        elif "Authentication is required" in stderr:
            raise DownloadError("Al says: That video is behind a velvet rope! I need a VIP pass (auth) to get in.")
        else:
            error_details = stderr.split(':')[-1].strip() or stdout.split('\n')[-1].strip() or "The internet tubes are clogged!"
            raise DownloadError(f"Something went wrong while I was scoping out the video: {error_details}")

def download_video(url, output_dir):
    """Downloads video using yt-dlp."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Template: Title [id].ext
    output_template = os.path.join(output_dir, '%(title)s [%(id)s].%(ext)s')
    
    try:
        # Download format: best video+audio that is mp4 compatible or anything else we can merge
        command = [
            *YT_DLP_CMD, 
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 
            '-o', output_template, 
            '--merge-output-format', 'mp4',
            url
        ]
        subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        
        # Find the downloaded file
        info = get_video_info(url)
        if info:
            video_id = info.get('id')
            # Simple search for the file with the ID in the name in the output dir
            for file in os.listdir(output_dir):
                if video_id in file:
                    return os.path.join(output_dir, file)
        return None
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        stdout = e.stdout or ""
        logger.error(f"Error downloading video:\nStdout: {stdout}\nStderr: {stderr}")
        error_details = stderr.split(':')[-1].strip() or stdout.split('\n')[-1].strip() or "Al's accordion is jammed!"
        raise DownloadError(f"The download failed! My digital bellows popped: {error_details}")
    except VideoHandlerError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during download: {e}")
        raise DownloadError(f"Even I don't know what happened there! *Accordion screech*")

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
    
    try:
        # Get duration
        probe = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path
        ], capture_output=True, text=True, check=True, encoding='utf-8')
        duration = float(probe.stdout.strip())
        
        # Target bitrate = target size / duration
        target_total_bitrate = (target_size_mb * 8 * 1024 * 1024) / duration
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
            '-f', 'mp4',
            '-movflags', '+faststart',
            '-pix_fmt', 'yuv420p',
            dev_null
        ]
        subprocess.run(command, check=True)
        
        # Pass 2
        command = [
            FFMPEG_CMD, '-y',
            '-i', input_path,
            '-c:v', 'libx264',
            '-b:v', str(int(video_bitrate)),
            '-pass', '2',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-pix_fmt', 'yuv420p',
            output_path
        ]
        subprocess.run(command, check=True)
        
        # Cleanup pass logs
        for f in os.listdir('.'):
            if f.startswith('ffmpeg2pass'):
                try: os.remove(f)
                except: pass
        
        return output_path

    except Exception as e:
        logger.error(f"Normalization/Compression failed: {e}")
        # If normalization fails, we still want to try sending the original
        return input_path 

def process_video(url):
    """Main workflow for a video URL."""
    # 1. Check Archive
    archived_path = check_archive(url)
    if archived_path and os.path.exists(archived_path):
        logger.info(f"Found in archive: {archived_path}")
        return archived_path

    temp_dir = os.path.join(os.getcwd(), 'temp_download')
    try:
        # 2. Download
        downloaded_path = download_video(url, temp_dir)
        if not downloaded_path:
            return None

        # 3. Always Normalize/Compress for iOS (unless archived)
        final_path = compress_video(downloaded_path, MAX_SIZE_MB, force_normalize=True)

        # 4. Archive
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        archive_dir = os.path.join(ARCHIVE_ROOT, timestamp)
        os.makedirs(archive_dir, exist_ok=True)
        
        filename = os.path.basename(final_path)
        archived_file_path = os.path.join(archive_dir, filename)
        
        shutil.move(final_path, archived_file_path)
        
        # Update index
        index = load_archive_index()
        index[url] = archived_file_path
        save_archive_index(index)
        
        return archived_file_path

    except Exception as e:
        logger.error(f"Failed to process video {url}: {e}")
        return None
    finally:
        # Always cleanup temp
        if os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except: pass

# Verify dependencies on module load
try:
    check_dependencies()
except Exception as e:
    logger.error(f"CRITICAL ERROR: {e}")
