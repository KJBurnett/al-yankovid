# Installation and Onboarding Roadmap

This roadmap is for making a first installation reliable without changing the
working paths used by existing installations. Complete each item behind
compatible defaults, document an upgrade/rollback path, and add regression
coverage before changing persisted data or startup behavior.

## P0 — Prevent first-run and upgrade failures

- [ ] **Make the published Docker image the documented default install.** Provide
  one maintained quick-start path using the `:stable` image, a copied `.env`,
  named or explicit persistent volumes, and an explicit first-run registration
  or linking flow. Keep `docker-compose.yml`, `DOCKER_README.md`, the README,
  and the UnRAID instructions consistent.
- [ ] **Add a startup preflight with actionable diagnostics.** Before starting
  the bot, validate required settings, writable `data`/`archive`/`logs`
  directories, `signal-cli`, Java, and `ffmpeg`. Distinguish an unlinked Signal
  account from a bad configuration, print safe recovery commands, and use a
  clear non-zero exit status for unrecoverable errors.
- [ ] **Fix the non-root auto-update contract.** The UnRAID compose file runs
  as `PUID:PGID`, while the boot-time `signal-cli` updater replaces files under
  `/opt`. Ensure an update cannot terminate startup when that location is not
  writable. Preserve the current update-by-default behavior for existing
  root-based deployments, and offer a documented safe default for non-root
  installs.
- [ ] **Add a supported health check and readiness signal.** Expose a
  container-level health check that reports ready only after dependencies and
  Signal account availability are verified. Document how installers can use it
  to diagnose a container that is running but cannot receive messages.
- [ ] **Replace placeholder-sensitive configuration with generated,
  validated configuration.** Keep every existing environment variable and its
  default, add missing documented variables such as `BOT_UUID`,
  `SIGNAL_CLI_CONFIG_DIR`, archive/log paths, timezone, ownership, and
  `SIGNAL_CLI_AUTO_UPDATE`, and fail clearly for placeholder bot numbers. Do
  not put real server URLs or credentials in example files.

## P1 — Make setup self-service

- [ ] **Provide a platform-neutral Signal linking workflow.** Document both
  dedicated-number registration and linked-device setup with matching configuration
  paths. Avoid requiring users to send QR payloads to third-party QR websites;
  provide a local/terminal QR option or explain a trusted local alternative.
- [ ] **Add an interactive installer or setup validator.** It should create
  `.env` from the example without overwriting an existing file, check tools and
  storage permissions, collect only non-secret settings, and print the exact
  next command. It must be optional so scripted and existing deployments keep
  working unchanged.
- [ ] **Make local Windows, macOS, and Linux support explicit.** Correct the
  platform-specific `signal-cli` executable examples, Java requirements, and
  shell prerequisites. Ensure `run.sh` reports a missing virtual environment
  or dependencies instead of failing at `source`.
- [ ] **Publish a configuration reference and troubleshooting matrix.** Map
  each environment variable to its default, scope, and restart requirement.
  Include common symptoms such as permissions, unregistered accounts, Signal
  compatibility updates, no writable archive, oversized uploads, and
  Rocket.Chat connection failures.
- [ ] **Document backup, upgrade, and rollback procedures.** State exactly
  which persistent files and directories must be backed up, how to pin an
  image or `signal-cli` version, and how to revert without losing archive,
  stats, user mappings, or Signal registration.

## P2 — Improve release confidence and maintenance

- [ ] **Version and pin runtime dependencies deliberately.** Publish a tested
  compatibility matrix for Python, Java, `signal-cli`, `yt-dlp`, and supported
  CPU architectures. Retain an opt-in/latest route for urgent Signal protocol
  updates, but give new users a reproducible stable path.
- [ ] **Add installation smoke coverage to CI.** Build the image for supported
  architectures, verify Java/`signal-cli`/`ffmpeg`, run the entrypoint with
  empty and pre-populated writable data volumes, and assert that no secrets or
  account data enter the image.
- [ ] **Add a release checklist.** Require a fresh-install test, an in-place
  upgrade test retaining `data` and `archive`, a rollback test, documentation
  review, and a stable image/tag before calling a release supported.
- [ ] **Offer deployment templates without making them mandatory.** Maintain
  examples for Docker Compose, UnRAID, and optional Rocket.Chat that use the
  same environment-variable contract and persistent-volume layout.

## Backward-compatibility guardrails

- [ ] Never rename, relocate, or reinterpret existing environment variables,
  `/app/data`, `/app/archive`, `/app/logs`, `stats.json`, `users_map.json`, or
  archive index entries without a migration that is idempotent, backed up, and
  reversible.
- [ ] Keep Signal-only operation the default; Rocket.Chat must remain disabled
  unless explicitly enabled.
- [ ] Preserve current container and local launch commands during any
  transition. New onboarding tools and health checks must be additive.
- [ ] Test upgrades against representative legacy `data` and `archive`
  directories before release, including permissions owned by the configured
  PUID/PGID.
