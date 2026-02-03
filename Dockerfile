FROM python:3.10-slim

# Install system dependencies
# ffmpeg: Video processing
# default-jre: Java Runtime for signal-cli
# curl, wget, tar: Downloading utilities
# libmagic1: Often needed for python-magic (if used later)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    default-jre \
    curl \
    wget \
    tar \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Set up Signal-CLI environment
ENV SIGNAL_CLI_VERSION=0.13.3
ENV SIGNAL_CLI_HOME=/opt/signal-cli
ENV PATH=$PATH:$SIGNAL_CLI_HOME/bin

# Download and install Signal-CLI
RUN cd /opt && \
    wget https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux.tar.gz && \
    tar xf signal-cli-${SIGNAL_CLI_VERSION}-Linux.tar.gz && \
    rm signal-cli-${SIGNAL_CLI_VERSION}-Linux.tar.gz && \
    mv signal-cli-${SIGNAL_CLI_VERSION} signal-cli

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
