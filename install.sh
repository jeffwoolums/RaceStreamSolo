#!/bin/bash
#
# RaceStream Solo Installer
# One-command installation for Raspberry Pi
#

set -e

echo "============================================"
echo "  RaceStream Solo Installer"
echo "  Standalone Multi-Camera YouTube Streamer"
echo "============================================"
echo ""

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check for root
if [ "$EUID" -eq 0 ]; then
    echo "Please don't run as root. The script will use sudo when needed."
    exit 1
fi

echo "Step 1/5: Updating system packages..."
sudo apt-get update

echo ""
echo "Step 2/5: Installing Docker..."
if command -v docker &> /dev/null; then
    echo "Docker already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "Docker installed successfully"
fi

echo ""
echo "Step 3/5: Installing Docker Compose..."
if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    echo "Docker Compose already installed"
else
    sudo apt-get install -y docker-compose-plugin
    echo "Docker Compose installed successfully"
fi

echo ""
echo "Step 4/5: Setting up RaceStream Solo..."
INSTALL_DIR="/home/$USER/racestream-solo"

if [ -d "$INSTALL_DIR" ]; then
    echo "Installation directory exists. Updating..."
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || true
else
    echo "Cloning RaceStream Solo..."
    git clone https://github.com/jeffwoolums/RaceStreamSolo.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Create logs directory
mkdir -p "$INSTALL_DIR/logs"

echo ""
echo "Step 5/5: Building and starting container..."
cd "$INSTALL_DIR"
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d

# Get IP address
IP_ADDR=$(hostname -I | awk '{print $1}')

echo ""
echo "============================================"
echo "  Installation Complete!"
echo "============================================"
echo ""
echo "  Web UI: http://$IP_ADDR:8080"
echo ""
echo "  Next steps:"
echo "  1. Open the Web UI in your browser"
echo "  2. Click 'Scan for Cameras' to detect your USB cameras"
echo "  3. Enter your YouTube stream key"
echo "  4. Click 'Start Stream'"
echo ""
echo "  To view logs:"
echo "    docker logs -f racestream-solo"
echo ""
echo "  To restart:"
echo "    cd $INSTALL_DIR && docker compose -f docker/docker-compose.yml restart"
echo ""
echo "  To stop:"
echo "    cd $INSTALL_DIR && docker compose -f docker/docker-compose.yml down"
echo ""
echo "============================================"
