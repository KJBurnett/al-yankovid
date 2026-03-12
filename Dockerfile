FROM python:3.10-slim

# Install system dependencies
# ffmpeg: Video processing
# openjdk-21-jre-headless: Java Runtime for signal-cli (Java 21+)
# curl, wget, tar: Downloading utilities
# libmagic1: Often needed for python-magic (if used later)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    openjdk-21-jre-headless \
    curl \
    wget \
    tar \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Set up Signal-CLI environment
ENV SIGNAL_CLI_VERSION=0.13.23
ENV SIGNAL_CLI_HOME=/opt/signal-cli
ENV PATH=$PATH:$SIGNAL_CLI_HOME/bin

# Install signal-cli from GitHub releases
RUN wget -q "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}.tar.gz" \
    -O /tmp/signal-cli.tar.gz \
    && tar -xzf /tmp/signal-cli.tar.gz -C /opt/ \
    && mv /opt/signal-cli-${SIGNAL_CLI_VERSION} /opt/signal-cli \
    && rm /tmp/signal-cli.tar.gz

# Verify signal-cli installation
RUN signal-cli --version

# Set up working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for persistence (mapped volumes)
RUN mkdir -p /app/data /app/archive /app/logs

# Set permissions (optional, good for Unraid/Docker)
RUN chmod +x run.sh

# Environment variables (overridable via docker-compose)
ENV PYTHONUNBUFFERED=1
ENV LOGS_DIR=/app/logs
ENV ARCHIVE_ROOT=/app/archive
ENV SIGNAL_CLI_CONFIG_DIR=/app/data

# Entrypoint script to handle startup checks
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
