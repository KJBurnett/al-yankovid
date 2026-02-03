import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Configuration Variables
BOT_NUMBER = os.getenv('BOT_NUMBER', '+1234567890')
JAVA_HOME = os.getenv('JAVA_HOME', 'C:\\Path\\To\\Java')
MAX_SIZE_MB = int(os.getenv('MAX_SIZE_MB', '75'))
UPLOAD_LIMIT_MB = 98 # Hard limit for Signal uploads (approx 100MB)
SIGNAL_CLI_PATH = os.getenv('SIGNAL_CLI_PATH', './signal-cli-x.x.x/bin/signal-cli.bat')

# Ensure absolute path for signal-cli if relative
if SIGNAL_CLI_PATH.startswith('./'):
    SIGNAL_CLI_PATH = os.path.join(os.getcwd(), SIGNAL_CLI_PATH[2:])

# Archive Configuration
ARCHIVE_ROOT = os.getenv('ARCHIVE_ROOT', os.path.join(os.getcwd(), 'archive'))
TEMP_DOWNLOAD_DIR = os.path.join(os.getcwd(), 'temp_download')
LOGS_DIR = os.getenv('LOGS_DIR', os.path.join(os.getcwd(), 'logs'))

# Data Persistence (Stats, Maps, Signal Config)
# Default to ./data locally, or /app/data in Docker
DATA_DIR = os.getenv('SIGNAL_CLI_CONFIG_DIR', os.path.join(os.getcwd(), 'data'))
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

STATS_FILE = os.path.join(DATA_DIR, 'stats.json')
USERS_MAP_FILE = os.path.join(DATA_DIR, 'users_map.json')

