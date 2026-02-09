Migration guide: Move current Windows instance -> unRAID container

This document provides a step-by-step checklist to migrate an existing Windows-run Al YankoVid instance into an UnRAID Docker container while preserving `./data` and `./archive`.

Pre-steps (on Windows)
1. Stop the bot on Windows and create backups:
   - Zip or tar `./data` and `./archive` and copy them to an external location.
   - Verify `data/users_map.json`, `data/stats.json`, and the signal-cli config subfolder exist.

Prepare UnRAID host
1. On UnRAID, create an appdata folder for the app (example):
   - `/mnt/user/appdata/al-yankovid/` with subfolders `data`, `archive`, and `logs`.
   - Ensure the share is accessible from the Windows machine (or use a USB/SSH copy method).

Copy data
1. Copy Windows `./data` -> UnRAID `/mnt/user/appdata/al-yankovid/data`.
   - Recommended: use SMB share (map a network drive on Windows) and then use robust copy (e.g., `robocopy`) or copy via rsync from another Linux host.
2. Copy Windows `./archive` -> UnRAID `/mnt/user/appdata/al-yankovid/archive`.
3. Verify file integrity (sizes, presence of index.json, and per-user folders).

Permissions
1. On UnRAID, set ownership to the UID/GID you will run the container as (or set PUID/PGID env vars in container settings):
   - `chown -R 1000:1000 /mnt/user/appdata/al-yankovid` (replace 1000 with your PUID/PGID)

Start container (local compose)
1. Update `docker-compose.unraid.yml` host paths if needed.
2. Set environment variables in UnRAID container config (BOT_NUMBER, PUID, PGID, TZ).
3. Start the container via UnRAID UI or CLI:
   - `docker-compose -f docker-compose.unraid.yml up --build -d`

Register / Link signal-cli (first run)
1. If `/app/data` is empty or does not contain signal-cli registration, exec into the container and link:
   - `docker exec -it al-yankovid /bin/bash`
   - `signal-cli --config /app/data link -n "UnRAID-Al"`
   - Scan the QR on your phone to link; or use `register`/`verify` flows if creating a new number.

Validation
1. Confirm the bot starts and finds the signal-cli config (check logs in `/app/logs`).
2. Send a test `Yank {url}` or simulate a message to ensure a video is downloaded and archived in `/app/archive` and index.json is updated.
3. Verify `data/users_map.json` and `data/stats.json` migrated correctly.

Cutover & Rollback
1. Once validated, stop the Windows instance to avoid duplicate processing.
2. Keep backups for at least several days. If anything fails, restore the `data` and `archive` from backups and start the Windows instance back up, or copy back the folders.

Troubleshooting notes
- If signal-cli fails after migration, confirm file permissions and that the Java runtime in the container meets the minimum required version.
- If messages are missing attachments, check `ffmpeg` availability and that compression succeeded (files under upload limit).

If you'd like, I can now:
- Update the Dockerfile to pin Java to a specific tested package (e.g., openjdk-21),
- Add PUID/PGID handling in `entrypoint.sh`, and
- Create a ready-to-import UnRAID Docker template JSON (if you provide target PUID/PGID and host paths).
