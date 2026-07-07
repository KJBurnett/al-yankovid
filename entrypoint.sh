#!/bin/bash
set -e

# Default to /app/data if not set
SIGNAL_CONFIG="${SIGNAL_CLI_CONFIG_DIR:-/app/data}"

# Check for Signal-CLI configuration
# The config usually lives in $SIGNAL_CONFIG/.local/share/signal-cli or directly in data depending on how it's mapped.
# We'll check if the directory is empty or if specific config files are missing.
if [ -z "$(ls -A $SIGNAL_CONFIG)" ]; then
    echo "======================================================================"
    echo "WARNING: Signal-CLI configuration directory appears empty!"
    echo "Path: $SIGNAL_CONFIG"
    echo ""
    echo "You need to link or register this device before the bot can start."
    echo ""
    echo "To link usage (Scanning QR code on primary device):"
    echo "  docker exec -it <container_name> signal-cli --config $SIGNAL_CONFIG link -n <device_name>"
    echo ""
    echo "To register a new number:"
    echo "  docker exec -it <container_name> signal-cli --config $SIGNAL_CONFIG -u <PHONE_NUMBER> register"
    echo "  docker exec -it <container_name> signal-cli --config $SIGNAL_CONFIG -u <PHONE_NUMBER> verify <CODE>"
    echo "======================================================================"
    # We don't exit here because the user might need the container running to exec into it.
    # Instead, we'll try to start the bot, which will likely fail/loop until config is present.
else
    echo "Signal configuration found in $SIGNAL_CONFIG"
fi

# --- Auto-update signal-cli to the latest release on boot (resilient) ---
# Signal periodically changes server behavior in ways that require an updated
# signal-cli (e.g. sealed-sender envelope changes). Keeping signal-cli current
# on each boot prevents the bot from silently dropping messages.
# Set SIGNAL_CLI_AUTO_UPDATE=false to disable.
SIGNAL_CLI_AUTO_UPDATE="${SIGNAL_CLI_AUTO_UPDATE:-true}"
if [ "$SIGNAL_CLI_AUTO_UPDATE" = "true" ]; then
    echo "Checking for signal-cli updates..."
    CURRENT_VERSION="$(cat /opt/signal-cli/VERSION 2>/dev/null || true)"
    LATEST_VERSION="$(curl -fsSL --max-time 15 https://api.github.com/repos/AsamK/signal-cli/releases/latest 2>/dev/null | sed -n 's/.*"tag_name": "v\([0-9][^"]*\)".*/\1/p' | head -n1)"
    if [ -z "$LATEST_VERSION" ]; then
        echo "Could not resolve latest signal-cli version (network issue?); keeping ${CURRENT_VERSION:-current}."
    elif [ "$LATEST_VERSION" = "$CURRENT_VERSION" ]; then
        echo "signal-cli is up to date (${CURRENT_VERSION})."
    else
        echo "Updating signal-cli ${CURRENT_VERSION:-unknown} -> ${LATEST_VERSION}..."
        if wget -q --timeout=60 "https://github.com/AsamK/signal-cli/releases/download/v${LATEST_VERSION}/signal-cli-${LATEST_VERSION}.tar.gz" -O /tmp/signal-cli.tar.gz \
           && tar -xzf /tmp/signal-cli.tar.gz -C /tmp; then
            rm -rf /opt/signal-cli.new
            mv "/tmp/signal-cli-${LATEST_VERSION}" /opt/signal-cli.new
            echo "${LATEST_VERSION}" > /opt/signal-cli.new/VERSION
            rm -rf /opt/signal-cli.old
            mv /opt/signal-cli /opt/signal-cli.old && mv /opt/signal-cli.new /opt/signal-cli
            rm -rf /opt/signal-cli.old
            echo "signal-cli updated to ${LATEST_VERSION}."
        else
            echo "signal-cli update download failed; keeping ${CURRENT_VERSION:-current}."
        fi
        rm -f /tmp/signal-cli.tar.gz
    fi
fi
# --- end signal-cli auto-update ---

if command -v signal-cli >/dev/null 2>&1; then
    SIGNAL_CLI_RUNTIME_VERSION="$(signal-cli --version 2>/dev/null | head -n 1 || true)"
    if [ -n "$SIGNAL_CLI_RUNTIME_VERSION" ]; then
        echo "Using $SIGNAL_CLI_RUNTIME_VERSION"
    fi
fi

# Ensure directories exist
mkdir -p /app/logs /app/data /app/archive

# If PUID/PGID provided, adjust ownership (useful on UnRAID)
if [ -n "${PUID:-}" ] && [ -n "${PGID:-}" ]; then
    echo "Adjusting ownership of /app/data, /app/archive, /app/logs to ${PUID}:${PGID}"
    chown -R "${PUID}:${PGID}" /app/data /app/archive /app/logs || true
fi

echo "Starting Al YankoVid..."
exec python bot.py
