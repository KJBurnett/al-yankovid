# Repository Guidelines

## Project Structure & Module Organization
Core application code lives at the repository root. [`bot.py`](/Users/kylerburnett/Workspace/al-yankovid/bot.py) handles Signal message intake and responses, [`video_handler.py`](/Users/kylerburnett/Workspace/al-yankovid/video_handler.py) manages `yt-dlp` downloads and `ffmpeg` normalization, and [`signal_manager.py`](/Users/kylerburnett/Workspace/al-yankovid/signal_manager.py) starts and talks to `signal-cli`. Shared configuration is in [`config.py`](/Users/kylerburnett/Workspace/al-yankovid/config.py), and stats/personality helpers are in [`stats_manager.py`](/Users/kylerburnett/Workspace/al-yankovid/stats_manager.py) and [`personality.py`](/Users/kylerburnett/Workspace/al-yankovid/personality.py). Tests live under [`tests/`](/Users/kylerburnett/Workspace/al-yankovid/tests).

## Build, Test, and Development Commands
Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

Run the bot locally with `./run.sh` on macOS/Linux or `run.bat` on Windows. Run the test suite with:

```bash
pytest -q
```

For container work, build with `docker build -t al-yankovid .` and use [`docker-compose.yml`](/Users/kylerburnett/Workspace/al-yankovid/docker-compose.yml) or [`docker-compose.unraid.yml`](/Users/kylerburnett/Workspace/al-yankovid/docker-compose.unraid.yml) as needed.

## Coding Style & Naming Conventions
Use 4-space indentation and follow existing Python style. Prefer small, focused functions and explicit exception handling around subprocess calls. Use `snake_case` for functions and variables, `UPPER_SNAKE_CASE` for module-level constants, and descriptive test names like `test_handle_video_request_success_path`.

## Testing Guidelines
This project uses `pytest`. Add or update tests for any behavior change, especially around download selection, ffmpeg processing, archive behavior, and bot messaging. Keep tests in `tests/test_<module>.py` and prefer monkeypatch-based unit coverage over real network or Signal calls.

## Commit & Pull Request Guidelines
Recent history favors short imperative commit subjects such as `Fix Dockerfile: download signal-cli at build time instead of COPY` and `Notify chat when yt-dlp update+retry is triggered`. Do not push directly to `main`. Create feature branches from a clean `main` using `user/kjburnett/<featurename>`, push that branch, and open a PR. PRs should summarize the behavior change, mention test coverage, and note any user-visible chat/output changes.

## Security & Configuration Tips
Never commit `.env`, `data/`, `archive/`, Signal registration files, or downloaded runtime artifacts. `signal-cli` should be installed locally or by Docker build, not checked into Git.
