#!/bin/bash
# Stop RaceStream Solo streaming

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Stopping RaceStream Solo..."

if [ -f "docker/docker-compose.yml" ]; then
    cd docker
    docker compose down
else
    pkill -f "solo_agent.py" || true
fi

echo "Stopped."
