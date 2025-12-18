#!/bin/bash
# RaceStream Solo Installation Script

set -e

echo "=== RaceStream Solo Installation ==="

# Check if running as root for some operations
if [ "$EUID" -ne 0 ]; then
    echo "Note: Some operations may require sudo"
fi

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "Docker installed. You may need to log out and back in."
fi

# Install v4l-utils for camera detection
echo "Installing v4l-utils..."
sudo apt-get update
sudo apt-get install -y v4l-utils

# Create directories
echo "Creating directories..."
mkdir -p ~/racestream-solo/{config,overlays/templates,logs,scripts}

# Copy files to home directory (if running from git clone)
if [ -f "../config/solo_config.yaml" ]; then
    echo "Copying configuration files..."
    cp -n ../config/solo_config.yaml ~/racestream-solo/config/ 2>/dev/null || true
fi

# Detect cameras
echo ""
echo "=== Detecting Cameras ==="
v4l2-ctl --list-devices 2>/dev/null || echo "No cameras detected"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit ~/racestream-solo/config/solo_config.yaml"
echo "   - Add your YouTube stream key"
echo "   - Configure camera devices"
echo "   - Set overlay options"
echo ""
echo "2. Add a logo (optional):"
echo "   - Copy your logo to ~/racestream-solo/overlays/logo.png"
echo ""
echo "3. Start streaming:"
echo "   cd ~/racestream-solo && ./scripts/start.sh"
echo ""
