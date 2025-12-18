#!/bin/bash
# Start RaceStream Solo streaming

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Starting RaceStream Solo..."

# Check if running in Docker
if [ -f "docker/docker-compose.yml" ]; then
    cd docker
    docker compose up -d --build
    echo ""
    echo "Started! View logs with: docker logs -f racestream-solo"
else
    # Run directly with Python
    echo "Running directly (no Docker)..."
    python3 agent/solo_agent.py
fi
