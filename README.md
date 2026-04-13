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
2.  **Extract**: Extract the `.tar.gz` file into the repository root. You should see a folder like `signal-cli-<version>`.
3.  **Configure**: Set `SIGNAL_CLI_PATH` in `.env` to match your installed version (for example `./signal-cli-<version>/bin/signal-cli.bat`).

### 4. Signal-cli Setup (Important!)
Al requires a separate Signal number. **Do not use your own number.**
1.  **Register a Number**: Use a Google Voice number or a burner.
2.  **Registering via CLI**:
    ```powershell
    # Register (replace +1234567890 with your bot's number)
    .\signal-cli-<version>\bin\signal-cli.bat -u +1234567890 register
    
    # Verify (enter the code sent to your phone)
    .\signal-cli-<version>\bin\signal-cli.bat -u +1234567890 verify CODE
    ```
3.  **Set a Profile Name**:
    ```powershell
    .\signal-cli-<version>\bin\signal-cli.bat -u +1234567890 updateProfile --name "Al YankoVid"
    ```

### Docker signal-cli behavior
- The Docker image resolves `SIGNAL_CLI_VERSION=latest` at build time by default.
- You can pin a specific version when building:
  ```bash
  docker build --build-arg SIGNAL_CLI_VERSION=0.13.26 -t al-yankovid:custom .
  ```
- If logs show a likely signal-cli compatibility failure, refresh and recreate:
  ```bash
  docker compose pull
  docker compose up -d --force-recreate
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

## Docker Images

Al YankoVid is published to the GitHub Container Registry (GHCR) and updated automatically on every push to `main`.

| Tag | Image | When it updates |
|---|---|---|
| `stable` | `ghcr.io/kjburnett/al-yankovid:stable` | Only when a versioned release is tagged (e.g. `v1.0.1`) |
| `latest` | `ghcr.io/kjburnett/al-yankovid:latest` | Every merge to `main` |
| `v1.0.1` | `ghcr.io/kjburnett/al-yankovid:v1.0.1` | Pinned to a specific release |

**Recommendation**: Use `:stable`. It only updates when a release is intentionally cut, so you won't be caught off guard by work-in-progress changes from `main`. Use `:latest` at your own risk — it always reflects the bleeding edge.

### Updating your container (unRAID)

Once your container is configured with a GHCR image, updating is one click: **Docker → al-yankovid → Update Container**. No tarballs, no manual steps.

---

## Migration & Deployment Notes (unRAID)

This repository was migrated to an unRAID container during development. Key actions and commands used during the migration are recorded here so you can reproduce the same setup.

Important: never commit runtime registration files or archives to the repository. The project .gitignore already excludes `data/` and `archive/`, but always verify before pushing.

1) Prepare host shares on unRAID
- Copy your existing `archive/` to a safe host path (example: `/mnt/user/drivepool/Containers/al-yankovid/archive`).
- Place the signal-cli runtime config (the `signal-cli` folder containing `data/`, `accounts.json`, `attachments/`, etc.) into your host `data` share (e.g., `/mnt/user/appdata/al-yankovid/data/signal-cli`).
- Ensure permissions: chown the host folders to the user you will run the container as (or use root):

```bash
# Example (run on unRAID host)
sudo chown -R 1000:1000 /mnt/user/appdata/al-yankovid
sudo chown -R 1000:1000 /mnt/user/drivepool/Containers/al-yankovid/archive
```

2) Transfer image to unRAID (alternative to building on host)
- Save locally-built image:

```bash
# On your build machine
docker save -o al-yankovid.tar al-yankovid:latest
# Copy al-yankovid.tar to your unRAID server (SCP, SMB, or move it to a share)
```

- Load on unRAID:

```bash
# On unRAID host
docker load -i /path/to/al-yankovid.tar
```

3) Run on unRAID (example)

```bash
docker run -d --name al-yankovid --restart unless-stopped \
  -e BOT_NUMBER='+16014365901' \
  -e SIGNAL_CLI_CONFIG_DIR=/app/data \
  -e SIGNAL_CLI_PATH=/opt/signal-cli/bin/signal-cli \
  -e JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  -e PUID=0 -e PGID=0 -e TZ='America/Los_Angeles' \
  -v /mnt/user/appdata/al-yankovid/data:/app/data:rw \
  -v /mnt/user/drivepool/Containers/al-yankovid/archive:/app/archive:rw \
  -v /mnt/user/appdata/al-yankovid/logs:/app/logs:rw \
  al-yankovid:latest
```

After start: verify with `docker logs -f al-yankovid` and ensure the bot reports "Signal-cli daemon started, waiting for messages".

4) Pushing code changes (recommended workflow)
- Create a branch for your changes using the convention `user/kjburnett/{featurename}`:

```bash
git checkout -b user/kjburnett/my-feature
# Make changes, then:
git add .
git commit -m "Description of changes"
git push origin user/kjburnett/my-feature
# Open a Pull Request on GitHub and merge to main
```

Merging to `main` automatically builds and publishes `:latest` via GitHub Actions.

- **Cutting a stable release**: Once `main` is in a good state, tag it with a version number. This updates both `:stable` and the pinned version tag (e.g. `:1.0.1`):

```bash
git checkout main && git pull
git tag v1.0.1
git push --tags
```

That's it — GitHub Actions picks up the tag push and handles the rest.

5) Final checklist before merging
- Verify `.gitignore` excludes `data/`, `archive/`, `.env` and any local-only artifacts.
- Run `git status` and `git diff` to ensure no credentials or registration files are present.
- Merge your branch to `main`, then (optionally) build and push an image tagged from `main` to your registry.

If you'd like, I can add a GitHub Actions workflow to build and optionally push images to Docker Hub on merge to `main` (keep in mind secrets for Docker Hub must be configured in GitHub).
