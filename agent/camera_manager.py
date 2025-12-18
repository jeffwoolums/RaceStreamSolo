#!/usr/bin/env python3
"""
RaceStream Solo Camera Manager
Dynamic camera detection and management.
Auto-detects USB cameras and manages hot-plug events.
"""

import os
import subprocess
import re
import time
import threading
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger('camera_manager')


@dataclass
class Camera:
    device: str  # /dev/video0
    name: str  # Friendly name
    model: str  # Camera model from v4l2
    resolutions: List[str] = field(default_factory=list)
    formats: List[str] = field(default_factory=list)
    enabled: bool = True
    is_capture: bool = True  # True if it's a video capture device
    audio_device: str = ""  # ALSA device like "hw:3"

    def best_resolution(self) -> str:
        """Get best available resolution."""
        preferred = ['1920x1080', '1280x720', '640x480']
        for res in preferred:
            if res in self.resolutions:
                return res
        return self.resolutions[0] if self.resolutions else '640x480'

    def supports_mjpeg(self) -> bool:
        """Check if camera supports MJPEG."""
        return 'MJPG' in self.formats or 'mjpeg' in str(self.formats).lower()

    def has_audio(self) -> bool:
        """Check if camera has audio."""
        return bool(self.audio_device)


class CameraManager:
    """Manages camera detection and monitoring."""

    def __init__(self):
        self.cameras: Dict[str, Camera] = {}
        self.lock = threading.Lock()
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._on_camera_change = None  # Callback for camera changes

    def set_change_callback(self, callback):
        """Set callback for when cameras change."""
        self._on_camera_change = callback

    def detect_cameras(self) -> List[Camera]:
        """Detect all available video capture devices."""
        cameras = []

        try:
            # Get list of devices
            result = subprocess.run(
                ['v4l2-ctl', '--list-devices'],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                logger.warning("v4l2-ctl failed, trying fallback detection")
                return self._fallback_detect()

            # Parse output - format is:
            # Camera Name (usb-xxx):
            #     /dev/video0
            #     /dev/video1
            current_model = "Unknown Camera"
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue

                if line.endswith(':'):
                    # This is a camera name line
                    current_model = line.rstrip(':').split('(')[0].strip()
                elif line.startswith('/dev/video'):
                    device = line
                    # Check if it's a capture device
                    if self._is_capture_device(device):
                        camera = self._get_camera_info(device, current_model)
                        if camera:
                            cameras.append(camera)

        except Exception as e:
            logger.error(f"Error detecting cameras: {e}")
            return self._fallback_detect()

        return cameras

    def _fallback_detect(self) -> List[Camera]:
        """Fallback detection by scanning /dev/video*."""
        cameras = []
        for i in range(20):
            device = f'/dev/video{i}'
            if os.path.exists(device) and self._is_capture_device(device):
                camera = self._get_camera_info(device, f"Camera {i}")
                if camera:
                    cameras.append(camera)
        return cameras

    def _is_capture_device(self, device: str) -> bool:
        """Check if device is a video capture device (not metadata/output)."""
        try:
            result = subprocess.run(
                ['v4l2-ctl', '-d', device, '--all'],
                capture_output=True, text=True, timeout=5
            )
            # Look for "Video Capture" capability
            return 'Video Capture' in result.stdout and 'video/output' not in result.stdout.lower()
        except:
            return False

    def _detect_audio_device(self, model: str) -> str:
        """Detect audio device for a camera by matching model name."""
        try:
            with open('/proc/asound/cards', 'r') as f:
                cards_info = f.read()

            model_lower = model.lower()

            for line in cards_info.split('\n'):
                if '[' in line and ']:' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        card_num = parts[0].strip()
                        card_name = line.split('- ')[1].strip().lower() if '- ' in line else ""

                        # Match by keywords from model name
                        model_keywords = ['osmo', 'gopro', 'action', 'hero']
                        for keyword in model_keywords:
                            if keyword in model_lower and keyword in card_name:
                                return f"hw:{card_num}"

                        # Try matching model words to card name
                        for word in model_lower.replace('_', ' ').split():
                            if len(word) > 3 and word in card_name:
                                return f"hw:{card_num}"

            return ""
        except Exception as e:
            logger.debug(f"Error detecting audio: {e}")
            return ""

    def _get_camera_info(self, device: str, model: str) -> Optional[Camera]:
        """Get detailed info about a camera."""
        try:
            # Get supported formats
            result = subprocess.run(
                ['v4l2-ctl', '-d', device, '--list-formats-ext'],
                capture_output=True, text=True, timeout=5
            )

            formats = []
            resolutions = []

            for line in result.stdout.split('\n'):
                # Look for format names like [0]: 'MJPG'
                if "'" in line:
                    match = re.search(r"'(\w+)'", line)
                    if match:
                        fmt = match.group(1)
                        if fmt not in formats:
                            formats.append(fmt)

                # Look for resolutions like "Size: Discrete 1920x1080"
                if 'Size:' in line:
                    match = re.search(r'(\d+)x(\d+)', line)
                    if match:
                        res = f"{match.group(1)}x{match.group(2)}"
                        if res not in resolutions:
                            resolutions.append(res)

            if not resolutions:
                resolutions = ['640x480']  # Default fallback

            # Generate friendly name
            dev_num = device.replace('/dev/video', '')
            friendly_name = f"cam{dev_num}"

            # Detect audio device
            audio_device = self._detect_audio_device(model)

            return Camera(
                device=device,
                name=friendly_name,
                model=model,
                resolutions=resolutions,
                formats=formats,
                is_capture=True,
                audio_device=audio_device
            )

        except Exception as e:
            logger.error(f"Error getting camera info for {device}: {e}")
            return None

    def refresh(self) -> List[Camera]:
        """Refresh camera list and detect changes."""
        new_cameras = self.detect_cameras()

        with self.lock:
            old_devices = set(self.cameras.keys())
            new_devices = set(c.device for c in new_cameras)

            added = new_devices - old_devices
            removed = old_devices - new_devices

            # Update camera dict
            self.cameras = {c.device: c for c in new_cameras}

            if added or removed:
                logger.info(f"Camera change detected - Added: {added}, Removed: {removed}")
                if self._on_camera_change:
                    self._on_camera_change(list(self.cameras.values()), list(added), list(removed))

        return new_cameras

    def get_cameras(self) -> List[Camera]:
        """Get current list of cameras."""
        with self.lock:
            return list(self.cameras.values())

    def get_camera(self, device: str) -> Optional[Camera]:
        """Get camera by device path."""
        with self.lock:
            return self.cameras.get(device)

    def start_monitoring(self, interval: float = 5.0):
        """Start monitoring for camera changes."""
        if self._monitoring:
            return

        self._monitoring = True

        def monitor_loop():
            while self._monitoring:
                self.refresh()
                time.sleep(interval)

        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"Camera monitoring started (interval: {interval}s)")

    def stop_monitoring(self):
        """Stop monitoring for camera changes."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
        logger.info("Camera monitoring stopped")

    def generate_config(self) -> Dict:
        """Generate camera config for solo_config.yaml."""
        cameras_config = []
        for camera in self.get_cameras():
            cameras_config.append({
                'device': camera.device,
                'name': camera.name,
                'model': camera.model,
                'resolution': camera.best_resolution(),
                'fps': 30,
                'enabled': camera.enabled,
                'format': 'mjpeg' if camera.supports_mjpeg() else 'yuyv'
            })
        return {'cameras': cameras_config}


def main():
    """Test camera detection."""
    logging.basicConfig(level=logging.INFO)

    manager = CameraManager()
    cameras = manager.detect_cameras()

    print(f"\nFound {len(cameras)} camera(s):\n")
    for cam in cameras:
        print(f"  {cam.device}: {cam.model}")
        print(f"    Name: {cam.name}")
        print(f"    Formats: {cam.formats}")
        print(f"    Resolutions: {cam.resolutions}")
        print(f"    Best resolution: {cam.best_resolution()}")
        print(f"    MJPEG support: {cam.supports_mjpeg()}")
        print()


if __name__ == '__main__':
    main()
