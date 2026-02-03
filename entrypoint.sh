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

# Ensure log directory exists
mkdir -p /app/logs

echo "Starting Al YankoVid..."
exec python bot.py
