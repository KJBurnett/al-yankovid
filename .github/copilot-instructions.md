# Copilot instructions for al-yankovid

This file helps future Copilot sessions by documenting how to build/run the project, a high-level architecture summary, and codebase-specific conventions.

## 1) Build, test, and lint commands

- Build and run via Docker (recommended):

```bash
# Build image
docker build -t al-yankovid .

# Or with compose (recommended for development)
docker-compose up --build -d
```

- Run locally (Windows):

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe bot.py
```

- Run locally (Linux / macOS):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 bot.py
```

- Tests / Lint:
  - No test framework or linter configuration detected in the repository. If you add pytest, run a single test with:

```bash
pytest path/to/test_file.py::test_name
```

  - If you add a linter (e.g., flake8), run it against a single file with:

```bash
flake8 path/to/file.py
```

## 2) High-level architecture

- bot.py: Main process and message router. Starts the Signal daemon via signal_manager and runs a worker thread that sequentially processes video requests.
- signal_manager.py: Starts/manages the signal-cli daemon (JSON-RPC) and provides helper functions to send messages.
- video_handler.py: Downloads (yt-dlp), normalizes/compresses (ffmpeg), archives videos and updates archive index.
- stats_manager.py: Records successes/failures and provides formatted stats messaging.
- config.py: Loads environment variables and sets DATA_DIR, ARCHIVE_ROOT, LOGS_DIR, and SIGNAL_CLI_PATH defaults.
- entrypoint.sh / Dockerfile / docker-compose.yml: Container startup and volume mappings for `/app/data` and `/app/archive`.

Data flow: signal-cli -> bot (stdin/stdout JSON) -> queue -> video_handler -> archive -> signal-cli sends message with attachment.

## 3) Key conventions & repo-specific notes

- Persistence locations:
  - `DATA_DIR` (`/app/data` in container) holds signal-cli config, `users_map.json`, and `stats.json`.
  - `ARCHIVE_ROOT` (`/app/archive`) holds per-user timestamped folders and `index.json` that maps original URLs to archived paths.
  - docker-compose.yml maps `./data:/app/data` and `./archive:/app/archive` by default—keep these mapped when migrating.

- Platform-specific code to watch for when changing behavior:
  - `config.py` default `SIGNAL_CLI_PATH` references a Windows `.bat` file if left relative. Use env vars when running in Linux containers.
  - `video_handler.py` tries `sys.prefix\Scripts\yt-dlp.exe` on Windows and falls back to `yt-dlp` for POSIX. It also handles `NUL` vs `/dev/null` and Windows-specific locking retries.
  - `bot.py` uses `taskkill` on Windows when terminating a child process; look for `os.name == 'nt'` checks when making changes.
  - `entrypoint.sh` intentionally prints guidance if the Signal config directory is empty—admins must exec into the container to `link`/`register` the device when first run.

- Dockerfile notes:
  - `SIGNAL_CLI_VERSION` is an ENV in the Dockerfile; repo also contains `signal-cli-0.13.23`—ensure these are in sync.
  - The Dockerfile currently installs `default-jre`; the README mentions Java 21+. Prefer pinning to a tested package (e.g., `openjdk-21-jre-headless`).

- UnRAID advice (for maintainers):
  - Map UnRAID shares to `/app/data` and `/app/archive`.
  - Consider adding `PUID`/`PGID` support and a chown step in `entrypoint.sh` to avoid permission issues.
  - Use `restart: unless-stopped` in your unRAID container settings and resource limits (ffmpeg can be memory/cpu intensive).

## 4) Where to look first when editing
- Files: `bot.py`, `video_handler.py`, `signal_manager.py`, `config.py`, `entrypoint.sh`, `Dockerfile`, `docker-compose.yml`.

## 5) Assistant config files
- No CLAUDE.md, .cursorrules, AGENTS.md, or other assistant configs were found in the repository.

## 6) Short checklist for migration to unRAID
- Ensure `signal-cli` version and Java version are consistent and compatible.
- Copy (`./data`, `./archive`) to UnRAID shares and bind-mount them into the container.
- Test registration/linking in the container and run a full end-to-end `Yank {url}` validation.

---

If you want this file expanded (more examples, common troubleshooting, or an unRAID templates section), say which area to cover.
