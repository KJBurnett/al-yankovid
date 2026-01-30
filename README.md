# Al YankoVid - Signal Video Bot 🪗🎭

A whacky Signal bot that listens for `Yank {url}` commands or `@mentions`, downloads the video using `yt-dlp`, optimizes it for Signal/iOS with `ffmpeg`, and pops it back into the chat with a "Weird Al" inspired quip!

## Features
- **Fast Downloading**: Uses `yt-dlp` to pull from almost any site.
- **iOS Optimized**: Automatically encodes with `+faststart` and `yuv420p` for instant play on mobile.
- **Auto-Cleanup**: Keeps your space clean by purging temp files.
- **Archive System**: Remembers what it yanked to save bandwidth.
- **Personality**: Over 50 whacky quips and 30+ custom download acknowledgments.
- **Resilient**: Auto-restarts if the Signal daemon crashes.

## Prerequisites
- **Java 21+**: Required for `signal-cli`.
- **FFmpeg**: Required for video optimization.
- **Python 3.10+**: For the bot logic.

## Setup

### 1. Repository Configuration
1.  **Clone the repo**.
2.  **Create your Environment File**:
    - Copy `.env.example` to `.env`.
    - Fill in your `BOT_NUMBER` (use a dedicated Google Voice number!).
    - Update `JAVA_HOME` with the path to your Java installation.

### 2. Python Dependencies
```powershell
# Windows
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# Mac / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Signal-cli Installation
1.  **Download**: Get the latest `signal-cli-x.xx.x.tar.gz` from the [official releases](https://github.com/AsamK/signal-cli/releases).
2.  **Extract**: Extract the `.tar.gz` file into the repository root. You should see a folder like `signal-cli-0.13.23`.
3.  **Configure**: Ensure the folder name match the version used in the following steps (and `signal_manager.py`).

### 4. Signal-cli Setup (Important!)
Al requires a separate Signal number. **Do not use your own number.**
1.  **Register a Number**: Use a Google Voice number or a burner.
2.  **Registering via CLI**:
    ```powershell
    # Register (replace +1234567890 with your bot's number)
    .\signal-cli-0.13.23\bin\signal-cli.bat -u +1234567890 register
    
    # Verify (enter the code sent to your phone)
    .\signal-cli-0.13.23\bin\signal-cli.bat -u +1234567890 verify CODE
    ```
3.  **Set a Profile Name**:
    ```powershell
    .\signal-cli-0.13.23\bin\signal-cli.bat -u +1234567890 updateProfile --name "Al YankoVid"
    ```

## Usage

### Starting the Bot
- **Windows**: Double-click `run.bat`.
- **Mac / Linux**: Run `./run.sh` (ensure it's executable: `chmod +x run.sh`).

### Stopping the Bot
Simply press **`Ctrl+C`** in the terminal window. This works on Windows, Mac, and Linux. Al will gracefully wind down his accordion and clean up his processes.

### Commands
-   **Manual**: Send `Yank {url}` in a DM or Group where the bot is a member.
-   **Mention**: Just tag `@Al YankoVid` followed by a `{url}` in a group chat.
-   **Greetings**: Say "Hi Al" or "How are you Al?" to see his whacky responses!

## Structure
-   `bot.py`: Main entry point and message router.
-   `signal_manager.py`: Handles the Signal JSON-RPC daemon.
-   `video_handler.py`: Logic for downloading and FFmpeg optimization.
-   `personality.py`: The brains behind the quips and polka-tastic attitude!
-   `config.py`: Loads settings from `.env`.
