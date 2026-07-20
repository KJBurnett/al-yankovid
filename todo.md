# Installation and Onboarding Roadmap

This roadmap turns the high-level P0/P1/P2 goals into a detailed, sequenced
implementation plan. It is the source of truth for *how* each item will be
built, not just *what* it is. Every item below follows the same shape:

- **Problem** — why this is needed today.
- **Approach** — the concrete implementation steps and the files/areas touched.
- **Compatibility contract** — exactly what must keep working, unchanged, for
  existing installs (Windows local run, root-based Docker Compose, and the
  UnRAID PUID/PGID compose file).
- **Testing** — how the change is verified before merge, including
  regression coverage against legacy state.
- **Rollback** — how an installer reverts if the change causes a problem.

Nothing in this plan may change the *meaning* of an existing environment
variable, rename a persisted file/directory, or make a previously optional
step mandatory. New behavior must be additive and default to today's
behavior unless an installer opts in.

## Ground truth (current behavior this plan must not break)

- `config.py` reads `BOT_NUMBER`, `BOT_UUID`, `JAVA_HOME`, `MAX_SIZE_MB`,
  `SIGNAL_CLI_PATH`, `ARCHIVE_ROOT`, `LOGS_DIR`, `SIGNAL_CLI_CONFIG_DIR`
  (aliased internally to `DATA_DIR`), and the `ROCKETCHAT_*` variables, each
  with a working default and `ROCKETCHAT_ENABLED` defaulting to `false`.
- `DATA_DIR` holds `stats.json`, `users_map.json`, and the `signal-cli`
  config; `ARCHIVE_ROOT` holds per-user timestamped folders plus
  `index.json`; both are created automatically if missing.
- `entrypoint.sh` warns (but does not exit) when `SIGNAL_CLI_CONFIG_DIR` is
  empty, optionally self-updates `signal-cli` under `/opt/signal-cli` when
  `SIGNAL_CLI_AUTO_UPDATE` is unset or `true`, `chown -R $PUID:$PGID` on
  `/app/data /app/archive /app/logs` only if both `PUID` and `PGID` are set,
  then execs `python bot.py`.
- `docker-compose.yml` runs as the image default user (root) with
  `./data|./archive|./logs` bind mounts and no `PUID`/`PGID`.
  `docker-compose.unraid.yml` sets `user: "${PUID:-1000}:${PGID:-1000}"` and
  points at `/mnt/user/appdata/al-yankovid/*`. Both must keep working as-is.
- The Dockerfile installs Java (Adoptium JRE, `JAVA_VERSION=25` by default)
  and `signal-cli` (`SIGNAL_CLI_VERSION=latest` by default) at build time
  into `/opt`, owned by root.
- `run.sh`/`run.bat` create/activate a local venv and run `bot.py` directly
  (no Docker) for Windows/macOS/Linux local development.

Any implementation step below that would touch these paths, variable names,
or defaults must instead add a new, separately-named variable/flag and keep
the old behavior as the default.

---

## P0 — Prevent first-run and upgrade failures

### P0.1 Make the published Docker image the documented default install

**Problem:** README, `DOCKER_README.md`, and the UnRAID docs each describe a
slightly different path (build-from-source vs. `ghcr.io` image, `.env` vs.
inline compose variables), so new installers can't tell which is current.

**Approach:**
1. Publish and tag `ghcr.io/kjburnett/al-yankovid:stable` alongside the
   existing `:latest` tag in the image-publish workflow (new/updated GitHub
   Actions workflow under `.github/workflows/`), pointed at the last
   release-checked commit (see P2.3). `:latest` keeps its current meaning
   (most recent build) so nothing that already pulls `:latest` changes
   behavior.
2. Add a single canonical quick-start section to `README.md` that: copies
   `.env.example` to `.env`, runs `docker compose up -d` against
   `docker-compose.yml` pinned to `:stable`, and links out to
   `DOCKER_README.md` for linking/registration and `MIGRATE_TO_UNRAID.md`
   for UnRAID-specific paths.
3. Cross-link `DOCKER_README.md`, `MIGRATE_TO_UNRAID.md`, and
   `docker-compose.unraid.yml`'s header comment to the same quick-start
   section instead of repeating divergent instructions.
4. Leave `docker-compose.yml`'s existing `image:` value
   (`ghcr.io/kjburnett/al-yankovid:latest`) untouched; only the
   documentation gains a `:stable` recommendation plus how to switch tags.

**Compatibility contract:** No change to volume paths, env var names, or the
`docker-compose.unraid.yml build: .` local-build flow. Existing users who
already have a running container and a `.env` are unaffected; this is a
docs/CI-only change plus one new image tag.

**Testing:** `docker compose config` validates both compose files still
parse; manually pull `:stable` and `:latest` and diff `docker inspect`
labels to confirm both resolve to a working image.

**Rollback:** Stop publishing `:stable`/remove the doc callout; `:latest`
and existing compose files are never modified, so there is nothing to
revert for existing installs.

### P0.2 Add a startup preflight with actionable diagnostics

**Problem:** `entrypoint.sh` only warns about an empty `signal-cli` config
directory; missing Java, `ffmpeg`, or an unwritable `data`/`archive`/`logs`
mount currently surfaces as a confusing Python traceback from `bot.py`.

**Approach:**
1. Add a new `preflight.py` (or a `--preflight` mode in `bot.py`) invoked
   from `entrypoint.sh` *before* `exec python bot.py`. It checks, in order:
   `signal-cli`/`java`/`ffmpeg` are on `PATH` and report versions; `data`,
   `archive`, `logs` (resolved the same way `config.py` resolves them) exist
   and are writable by the current UID; `BOT_NUMBER` is not the
   `.env.example` placeholder (`+1234567890`/`+12345678900`).
2. Print one categorized block per failure (`[MISSING TOOL]`,
   `[PERMISSION]`, `[UNLINKED ACCOUNT]`, `[PLACEHOLDER CONFIG]`) with the
   exact fix command, matching the existing link/register block style in
   `entrypoint.sh`.
3. Preflight failures that are recoverable at runtime (unlinked Signal
   account) keep the current non-fatal warn-and-continue behavior. Preflight
   failures that make the bot unable to run at all (no `ffmpeg`, unwritable
   volume) exit non-zero *before* `python bot.py` starts, so Docker's
   restart/health status reflects a real failure instead of a silent crash
   loop with a bare traceback.
4. Gate the "hard fail on unrecoverable error" behavior behind
   `PREFLIGHT_STRICT`, **defaulted to `false`** so a currently-working
   install's behavior is byte-for-byte unchanged (it never hits an
   unrecoverable condition, so this only matters for broken installs, but
   defaulting to `false` avoids any risk of a false-positive check turning a
   working install's warning into a hard failure). Installers can opt in to
   `PREFLIGHT_STRICT=true` for fail-fast CI/first-run validation.

**Compatibility contract:** A container that currently starts successfully
must still start successfully with identical logs plus the new preflight
banner; no new required env vars.

**Testing:** New `tests/test_preflight.py` covering: all-tools-present
happy path, missing `ffmpeg`, unwritable `archive` dir (chmod 000 in a temp
dir), placeholder `BOT_NUMBER`. Add an entrypoint smoke test (P2.2) that
runs the container against an empty vs. broken volume and asserts the exit
code/log content.

**Rollback:** Set `PREFLIGHT_STRICT=false` to fully restore today's
warn-only behavior without rebuilding.

### P0.3 Fix the non-root auto-update contract

**Problem:** `docker-compose.unraid.yml` runs the container as
`${PUID:-1000}:${PGID:-1000}`, but the Dockerfile installs `signal-cli` to
`/opt/signal-cli` owned by root, and `entrypoint.sh`'s auto-update block
`mv`s new files into `/opt/signal-cli` at boot. On UnRAID that `mv`/`rm -rf`
will fail silently or with a permission error inside the "resilient"
`if ... && ...` chain, which today just falls through to "keeping current
version" — safe, but only by accident, and not verified.

**Approach:**
1. In `entrypoint.sh`, before attempting the update, check
   `[ -w /opt/signal-cli ] && [ -w /opt ]`. If not writable, log
   `"signal-cli auto-update skipped: /opt is not writable by the current
   user (PUID/PGID). Set SIGNAL_CLI_AUTO_UPDATE=false to silence this, or
   run as root to allow in-place updates."` and continue startup exactly as
   today (this is already the de-facto behavior; this step makes it
   intentional and observable instead of an unlabeled failed `mv`).
2. Document a second, opt-in update mechanism for non-root installs: a
   `signal-cli` version baked in at image build time via `SIGNAL_CLI_VERSION`
   build-arg (already supported by the Dockerfile) plus a
   `docker compose pull && docker compose up -d` cadence, so non-root
   installers get updates through image tags instead of runtime `/opt`
   mutation.
3. Root-based `docker-compose.yml` installs keep today's default
   (`SIGNAL_CLI_AUTO_UPDATE=true`, writable `/opt`, updates happen) with no
   change.

**Compatibility contract:** `SIGNAL_CLI_AUTO_UPDATE` keeps its current
default and meaning for root installs. No new required variables for
UnRAID; the failure mode changes from "silent/ambiguous" to "logged and
still non-fatal."

**Testing:** Container smoke test running `entrypoint.sh` (or a stub) as a
non-root UID against a read-only `/opt` to assert the new log line appears
and the process still reaches `exec python bot.py`.

**Rollback:** Revert to the current unconditional attempt; behavior for
root installs is identical either way, so this is low-risk to ship or
revert independently.

### P0.4 Add a supported health check and readiness signal

**Problem:** There is no way for Docker/UnRAID to know the bot is actually
receiving Signal messages versus just "the process is running."

**Approach:**
1. Add a lightweight readiness marker: `bot.py`'s existing signal-cli
   JSON-RPC receive loop touches a file (e.g. `LOGS_DIR/healthy`) on each
   successful receive cycle, and on successful startup once the Signal
   daemon connection is confirmed.
2. Add a `HEALTHCHECK` to the Dockerfile that checks the marker's mtime is
   recent (e.g. a small `healthcheck.sh` using `find ... -mmin -5`), so it
   is dependency-free (no new Python/HTTP server needed) and does not open
   a new port.
3. Document the health status in `DOCKER_README.md` under a new
   "Diagnosing a stuck container" section, including what `docker inspect
   --format='{{json .State.Health}}' al-yankovid` reports and what to check
   (linked account, network egress) when it stays `unhealthy`.

**Compatibility contract:** Purely additive — no new ports, no new required
env vars, existing `docker-compose.yml`/`docker-compose.unraid.yml` need no
changes (Docker reads `HEALTHCHECK` from the image automatically). Installs
using `docker run` without compose still get the health check.

**Testing:** Build the image, start it against a valid linked account and
confirm `docker inspect` reports `healthy` within the check's start period;
start it against an empty `data` dir and confirm it stays `unhealthy` (never
receives) without crashing.

**Rollback:** Removing the `HEALTHCHECK` instruction fully reverts; no
persisted state depends on it (the marker file is disposable/regenerated).

### P0.5 Replace placeholder-sensitive configuration with generated, validated configuration

**Problem:** `.env.example` ships an obviously-fake `BOT_NUMBER` and a
Windows-style `JAVA_HOME`, and several env vars used by
`docker-compose*.yml` (`PUID`, `PGID`, `TZ`, `SIGNAL_CLI_AUTO_UPDATE`) are
not documented in `.env.example` at all.

**Approach:**
1. Extend `.env.example` to document every variable already consumed by
   `config.py`, `entrypoint.sh`, and both compose files —
   `BOT_UUID`, `SIGNAL_CLI_CONFIG_DIR`, `ARCHIVE_ROOT`, `LOGS_DIR`, `TZ`,
   `PUID`, `PGID`, `SIGNAL_CLI_AUTO_UPDATE` — each with its real default
   value from code (not a new value) and a one-line comment.
2. Keep every current default exactly as-is in `config.py`; this step only
   adds documentation/comments and, where a var was previously undocumented,
   adds it to `.env.example` with its already-implemented default.
3. Preflight (P0.2) is the enforcement point for "placeholder value" —
   `.env.example` itself stays example-only and is never read at runtime.

**Compatibility contract:** Zero code/default changes; documentation-only
diff to `.env.example` and a comment pass in `config.py` (no renames).

**Testing:** Diff every variable referenced via `os.getenv(` in `config.py`
against `.env.example` to confirm 1:1 coverage (can be a one-off grep-based
check run in CI, see P2.2).

**Rollback:** N/A — no behavior to revert.

---

## P1 — Make setup self-service

### P1.1 Provide a platform-neutral Signal linking workflow

**Problem:** `DOCKER_README.md` currently tells installers to paste the
`tsdevice:/?uuid=...` linking payload into a third-party site
(`the-qrcode-generator.com`) to render a QR code — an avoidable trust/privacy
issue since that string is a one-time credential to link the account.

**Approach:**
1. Add a local, offline QR rendering option: document
   `docker exec -it al-yankovid signal-cli --config /app/data link -n
   "<name>" --qr-code-output /app/logs/link-qr.png` (an already-supported
   `signal-cli` flag) so the PNG can be copied out of the mounted `logs`
   volume and scanned directly — no third-party site involved.
2. As a terminal-only fallback for installers without a way to view a PNG,
   document piping the linking URI through a local ASCII-QR tool (e.g. a
   `qrencode -t ANSIUTF8` one-liner run inside the container, added to the
   image only behind a `tools/` helper script so the base image size is
   unaffected for users who don't need it).
3. Keep the existing register/verify (dedicated number) flow in
   `DOCKER_README.md` unchanged; add it side-by-side with the linking flow
   so both paths are documented with matching `--config /app/data` usage.

**Compatibility contract:** No change to `entrypoint.sh` or `config.py`;
this is documentation plus an optional helper script, not a runtime
dependency change.

**Testing:** Manually verify `--qr-code-output` produces a scannable PNG
against a real `signal-cli` linked-device flow in a disposable test
account; confirm `DOCKER_README.md` examples copy/paste cleanly.

**Rollback:** Documentation-only; remove the section to revert.

### P1.2 Add an interactive installer or setup validator

**Problem:** New installers hand-edit `.env` with no feedback until the
container fails at runtime.

**Approach:**
1. Add an optional `tools/setup_wizard.py` (or `.sh`) that: copies
   `.env.example` to `.env` only if `.env` does not already exist (never
   overwrites), prompts for `BOT_NUMBER`, `TZ`, and whether to enable
   Rocket.Chat, validates the host paths that will be bind-mounted are
   creatable/writable, and prints the exact `docker compose up -d` command
   to run next.
2. Make it entirely optional and out of the default `ENTRYPOINT`/`CMD` —
   it is a one-time helper an installer runs manually
   (`python tools/setup_wizard.py` or `./tools/setup_wizard.sh`), never
   invoked by `entrypoint.sh`, so scripted/CI/existing deployments are
   unaffected.
3. Never prompt for or write secrets to any tracked file; `.env` stays
   git-ignored as it is today.

**Compatibility contract:** New opt-in file under `tools/`; zero changes to
`entrypoint.sh`, `Dockerfile` `ENTRYPOINT`, or existing compose files.

**Testing:** `tests/test_setup_wizard.py` using `tmp_path` to confirm it
never overwrites an existing `.env`, only writes documented variables, and
exits cleanly when run non-interactively with flags/env for CI.

**Rollback:** Delete `tools/setup_wizard.py`; no other file depends on it.

### P1.3 Make local Windows, macOS, and Linux support explicit

**Problem:** `run.sh`/`run.bat` and the README's local-run instructions
assume the venv and `signal-cli` binary already exist; failures show up as
raw shell errors (`No such file or directory` on `source`).

**Approach:**
1. Update `run.sh` and `run.bat` to check for the venv directory and
   `requirements.txt`-installed state before activating, printing a clear
   `"Run: python3 -m venv .venv && source .venv/bin/activate && pip install
   -r requirements.txt -r requirements-dev.txt"` (or the Windows equivalent)
   instead of failing at `source`/`call`.
2. Add an explicit per-OS `signal-cli` path/Java note next to
   `SIGNAL_CLI_PATH` and `JAVA_HOME` in `README.md` and `.env.example`
   (Windows `.bat` launcher vs. POSIX `signal-cli` script), matching what
   `config.py` already does at runtime (its relative-path resolution only
   assumes a `./`-prefixed value, which is OS-agnostic).
3. No change to `config.py`'s resolution logic — only documentation and the
   two run scripts' preflight messaging change.

**Compatibility contract:** `run.sh`/`run.bat` still `exec`/`call` the same
`python bot.py` at the end; the only change is a guarded, informative early
exit when prerequisites are missing, which cannot fire for an
already-working local setup.

**Testing:** Run `run.sh`/`run.bat` against a machine without a venv and
confirm the new guidance prints instead of a raw shell error; run again
after following the instructions to confirm the existing happy path is
unchanged.

**Rollback:** Revert the two scripts independently of any other change.

### P1.4 Publish a configuration reference and troubleshooting matrix

**Problem:** Env var defaults, scopes, and restart requirements are spread
across `config.py`, `.env.example`, and multiple markdown files with no
single reference; common failure symptoms aren't mapped to fixes anywhere.

**Approach:**
1. Add a `CONFIGURATION.md` with a table: variable, default (from
   `config.py`), what it controls, and whether changing it requires a
   restart-only or a rebuild (e.g. `SIGNAL_CLI_VERSION` is a build-arg and
   needs a rebuild; `MAX_SIZE_MB` is read at process start and needs a
   restart).
2. Add a troubleshooting table covering: permission-denied on `data`/
   `archive` (link to PUID/PGID guidance), unregistered/unlinked account
   (link to P1.1), `signal-cli` sealed-sender/NPE crashes after a Signal
   server change (matches the known `getServerGuid` issue fixed by
   `signal-cli` >= 0.14.5 — point installers at `SIGNAL_CLI_AUTO_UPDATE`/
   image rebuild), oversized uploads (`MAX_SIZE_MB` vs. the 100MB Signal
   ceiling already enforced by `UPLOAD_LIMIT_MB` in `config.py`), and
   Rocket.Chat connection failures (`ROCKETCHAT_*` vars, RC 8.0's
   `rooms.media` upload flow).
3. Link `CONFIGURATION.md` from `README.md`, `DOCKER_README.md`, and
   `MIGRATE_TO_UNRAID.md` instead of duplicating the variable list in each.

**Compatibility contract:** Documentation-only; no code or default changes.

**Testing:** N/A beyond doc review; optionally add the same CI variable-
coverage check from P0.5 to also assert every variable in
`CONFIGURATION.md` still exists in `config.py`.

**Rollback:** N/A.

### P1.5 Document backup, upgrade, and rollback procedures

**Problem:** `MIGRATE_TO_UNRAID.md` covers a one-time Windows-to-UnRAID
migration, but there is no general "how do I safely update this container"
doc for an installer who is already running it.

**Approach:**
1. Add an `UPGRADING.md` that states plainly: back up `data/` (contains
   `stats.json`, `users_map.json`, and the `signal-cli` config) and
   `archive/` (contains `index.json` and per-user media) before any image
   update; these directories are never touched by an image upgrade because
   they are bind-mounted, not baked into the image.
2. Document pinning: how to pin the image tag (`:stable`/a specific
   release tag from P0.1/P2.1) in `docker-compose.yml`'s `image:` line, and
   how to pin `signal-cli` via the Dockerfile's `SIGNAL_CLI_VERSION` build
   arg for installers who build locally.
3. Document rollback: re-point `image:` (or rebuild with the prior
   `SIGNAL_CLI_VERSION`) and restart — because `data`/`archive` are never
   migrated destructively per the guardrails below, rollback never requires
   restoring a backup unless the installer chooses to also revert
   `data`/`archive` state.

**Compatibility contract:** Documentation-only.

**Testing:** N/A beyond doc review and a manual pin/rollback dry run.

**Rollback:** N/A.

---

## P2 — Improve release confidence and maintenance

### P2.1 Version and pin runtime dependencies deliberately

**Problem:** The Dockerfile defaults `JAVA_VERSION=25` and
`SIGNAL_CLI_VERSION=latest`, so a fresh build today can silently pick up a
newer, untested Java or `signal-cli` release than the last one actually
verified.

**Approach:**
1. Add a `COMPATIBILITY.md` matrix recording the last-verified combination
   of Python (currently `python:3.10-slim` base), Java/Adoptium version,
   `signal-cli` version, `yt-dlp` version (from `requirements.txt`), and
   tested architectures (`amd64`, `arm64`, matching the Dockerfile's
   `TARGETARCH` handling).
2. Keep `SIGNAL_CLI_VERSION=latest` and `JAVA_VERSION=25` as the Dockerfile
   *build-arg defaults* (preserving today's behavior for anyone building
   from source without overrides), but have the `:stable` published image
   (P0.1) built with explicit, matrix-recorded values passed as build-args
   in CI, so the tagged artifact is reproducible even though the Dockerfile
   default stays "latest" for source builds.
3. Update the matrix as part of the release checklist (P2.3) whenever a new
   `:stable` is cut.

**Compatibility contract:** No Dockerfile default changes; purely a new doc
plus CI build-arg values used only for the `:stable` publish job.

**Testing:** CI job builds `:stable` with pinned args and runs the smoke
suite from P2.2 against it before pushing the tag.

**Rollback:** Re-run the publish job with the previous matrix's pinned
versions to re-cut `:stable`.

### P2.2 Add installation smoke coverage to CI

**Problem:** There is no automated check that the image actually boots,
finds its dependencies, and handles an empty vs. pre-populated data volume
correctly — regressions here currently surface only when a real user hits
them (e.g. the `signal-cli` sealed-sender crash, or a broken PUID/PGID
chown).

**Approach:**
1. Add a GitHub Actions job (new file under `.github/workflows/`, or a new
   job in the existing CI workflow) that: builds the image for `amd64` (and
   `arm64` via QEMU if already supported by the existing workflow), runs
   `docker run --rm <image> java -version`, `signal-cli --version`,
   `ffmpeg -version` to confirm all three are present, then runs the
   `entrypoint.sh` against (a) an empty `data` volume to assert the
   link/register warning prints and the process reaches `bot.py` without
   crashing, and (b) a generated-at-test-time `data`/`archive` volume (see
   step 3 below) to assert startup succeeds and no new files are created
   that would break a real `signal-cli` config.
2. Add a check that no secrets/account data are baked into the image layers
   (`docker history`/`docker save` + grep for `.env`, phone numbers, or
   `signal-cli` credential file patterns), guarding against a future
   `COPY . .` regression accidentally including a local `.env`/`data`.
3. Generate the fixture `data`/`archive` volumes at test time (e.g. a small
   `tests/fixtures/generate_signal_cli_fixture.py` that writes a minimal,
   clearly-fake `signal-cli` config with placeholder UUIDs/device IDs and a
   throwaway `stats.json`/`users_map.json`/`index.json`) instead of
   committing pre-built fixture files.
4. Run existing `pytest` suite (`tests/`) as part of the same workflow if
   not already wired in.

**Compatibility contract:** CI-only; no runtime behavior changes.

**Testing:** This *is* the testing infrastructure; validate by intentionally
breaking `entrypoint.sh` in a draft branch and confirming the job fails.

**Rollback:** Disable/remove the workflow job; no effect on shipped images.

### P2.3 Add a release checklist

**Problem:** There is no documented gate before calling an image/tag
"supported," so a `:stable` promotion (P0.1) needs a defined bar.

**Approach:**
1. Add a `RELEASE_CHECKLIST.md` requiring, before moving the `:stable` tag:
   a fresh-install test (empty volumes, follow `README.md` quick start,
   link a real or test Signal account, send a `Yank {url}` end to end), an
   in-place upgrade test using a fixture `data`/`archive` from the
   previous `:stable` (assert `stats.json`/`users_map.json`/`index.json`
   are read correctly, no re-linking required), a rollback test
   (re-point to the previous tag, confirm it still starts against the
   *upgraded* volume without corruption), a documentation review pass
   (README/DOCKER_README/CONFIGURATION/UPGRADING all reference the same
   version), and the P2.2 smoke suite passing.
2. Tie this checklist to the P0.1 `:stable` publish job as a required
   manual sign-off step (checkbox in the release PR description) until it
   is fully automated by P2.2.

**Compatibility contract:** Process/documentation only.

**Testing:** N/A — this defines the testing gate itself.

**Rollback:** N/A.

### P2.4 Offer deployment templates without making them mandatory

**Problem:** `docker-compose.yml` and `docker-compose.unraid.yml` already
exist but aren't presented as a matched, maintained pair with a consistent
contract; Rocket.Chat's opt-in variables are duplicated across both with no
single source describing them as optional.

**Approach:**
1. Keep both existing compose files as the maintained templates (no new
   competing format); add a short header comment to each (mirroring
   `docker-compose.unraid.yml`'s existing header style) stating they share
   the same environment-variable contract documented in
   `CONFIGURATION.md` (P1.4) and that `ROCKETCHAT_*` vars are optional and
   default disabled.
2. Add one more template only if a genuinely distinct deployment shape is
   needed (e.g. a `docker-compose.rocketchat.yml` example showing RC
   pre-enabled) — additive, never replacing the two existing files.

**Compatibility contract:** No changes to the volume paths, image
reference, or variable names in either existing compose file; header
comments and an optional new example file only.

**Testing:** `docker compose config` on every compose file in the repo to
confirm they still parse after edits.

**Rollback:** Revert header comments / delete the new example file
independently.

---

## Sequencing and dependencies

1. **P0 first, in order 0.5 → 0.2 → 0.3 → 0.4 → 0.1** — configuration
   documentation and preflight validation are prerequisites for writing
   accurate quick-start docs, and the auto-update fix should land before
   promoting a `:stable` tag that non-root installers will pull.
2. **P1 can proceed in parallel per item** once P0.2 (preflight) and P0.5
   (config reference source) exist, since P1.2 and P1.4 both build on them.
3. **P2.2 (CI smoke tests) should land before P2.1/P2.3** so every
   subsequent P1/P0 change is protected by regression coverage, even though
   it's listed last thematically.

## Backward-compatibility guardrails

- [ ] Never rename, relocate, or reinterpret existing environment variables,
  `/app/data`, `/app/archive`, `/app/logs`, `stats.json`, `users_map.json`,
  or archive index entries without a migration that is idempotent, backed
  up, and reversible. Every item above adds variables/files rather than
  renaming or repurposing existing ones.
- [ ] Keep Signal-only operation the default; Rocket.Chat must remain
  disabled unless explicitly enabled (`ROCKETCHAT_ENABLED=true`).
- [ ] Preserve current container and local launch commands during any
  transition (`docker compose up -d`, `exec python bot.py`, `run.sh`/
  `run.bat`). New onboarding tools, preflight checks, and health checks must
  be additive and never replace or gate the existing entrypoint/launch
  path for a currently-working install.
- [ ] Test upgrades against representative legacy `data` and `archive`
  directories (generated via the test-time fixture generator introduced in
  P2.2, never committed pre-built) before release, including permissions
  owned by the configured PUID/PGID and installs with no PUID/PGID set at
  all (root-based `docker-compose.yml`).
- [ ] Any change that touches `entrypoint.sh`, `Dockerfile`, or
  `config.py` must be reviewed against the "Ground truth" section above and
  called out explicitly in the PR description if it changes a default.
