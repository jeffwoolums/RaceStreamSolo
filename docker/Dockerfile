FROM python:3.11-slim-bookworm

# Install ffmpeg and v4l utilities
RUN apt-get update && apt-get install -y \
    ffmpeg \
    v4l-utils \
    fonts-dejavu-core \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY agent/ /app/agent/
COPY config/ /app/config/
COPY overlays/ /app/overlays/

# Create directories
RUN mkdir -p /app/logs /app/overlays/templates

# Environment
ENV PYTHONUNBUFFERED=1
ENV CONFIG_PATH=/app/config/solo_config.yaml

# Run web UI as main process - it will spawn the agent
CMD ["python", "/app/agent/web_ui.py"]
