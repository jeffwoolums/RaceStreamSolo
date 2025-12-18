#!/usr/bin/env python3
"""
RaceStream Solo Agent
Standalone dual-camera streaming agent with overlay support.
Can operate independently or integrate with RaceStream coordinator.
"""

import subprocess
import threading
import signal
import sys
import time
import os
import yaml
import logging
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('solo_agent')


class Mode(Enum):
    STANDALONE = "standalone"
    COORDINATOR = "coordinator"


@dataclass
class CameraConfig:
    device: str
    name: str
    resolution: str = "1920x1080"
    fps: int = 30
    enabled: bool = True
    audio_device: str = ""  # ALSA device like "hw:3" or empty for auto-detect


@dataclass
class OverlayConfig:
    enabled: bool = True
    text: str = ""
    text_position: str = "top-center"
    show_timestamp: bool = True
    font_size: int = 32
    font_color: str = "white"


@dataclass
class OutputConfig:
    platform: str = "youtube"
    rtmp_url: str = "rtmp://a.rtmp.youtube.com/live2"
    video_bitrate: str = "4500k"
    audio_bitrate: str = "128k"
    preset: str = "ultrafast"
    keyframe_interval: int = 2


class SoloAgent:
    """Main Solo streaming agent."""

    def __init__(self, config_path: str = "/app/config/solo_config.yaml"):
        self.config_path = config_path
        self.mode = Mode.STANDALONE
        self.cameras: List[CameraConfig] = []
        self.overlay = OverlayConfig()
        self.output = OutputConfig()
        self.stream_keys: Dict[str, str] = {}  # Per-camera stream keys
        self.coordinator_url: Optional[str] = None

        self.ffmpeg_processes: Dict[str, subprocess.Popen] = {}
        self.running = False
        self.lock = threading.Lock()

        # Rotation mode settings
        self.rotation_enabled = True
        self.rotation_interval = 15  # seconds
        self.current_camera_index = 0
        self.stream_key = ""  # Single stream key for rotation mode

        self.load_config()

    def load_config(self):
        """Load configuration from YAML file."""
        config_path = Path(self.config_path)
        if not config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}, using defaults")
            self._set_defaults()
            return

        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Mode
        mode_str = config.get('mode', 'standalone')
        self.mode = Mode.COORDINATOR if mode_str == 'coordinator' else Mode.STANDALONE
        self.coordinator_url = config.get('coordinator_url')

        # Cameras
        self.cameras = []
        for cam in config.get('cameras', []):
            self.cameras.append(CameraConfig(
                device=cam.get('device', '/dev/video0'),
                name=cam.get('name', 'camera'),
                resolution=cam.get('resolution', '1920x1080'),
                fps=cam.get('fps', 30),
                enabled=cam.get('enabled', True),
                audio_device=cam.get('audio_device', '')  # Empty means auto-detect
            ))

        # Output
        output = config.get('output', {})
        self.output = OutputConfig(
            platform=output.get('platform', 'youtube'),
            rtmp_url=output.get('rtmp_url', 'rtmp://a.rtmp.youtube.com/live2'),
            video_bitrate=output.get('video_bitrate', '4500k'),
            audio_bitrate=output.get('audio_bitrate', '128k'),
            preset=output.get('preset', 'ultrafast'),
            keyframe_interval=output.get('keyframe_interval', 2)
        )

        # Per-camera stream keys (YouTube dual ingest support)
        self.stream_keys = config.get('stream_keys', {})

        # Rotation settings
        rotation = config.get('rotation', {})
        self.rotation_enabled = rotation.get('enabled', True)
        self.rotation_interval = rotation.get('interval', 15)
        self.stream_key = rotation.get('stream_key', '')

        # Overlay
        overlay = config.get('overlay', {})
        self.overlay = OverlayConfig(
            enabled=overlay.get('enabled', True),
            text=overlay.get('text', ''),
            text_position=overlay.get('text_position', 'top-center'),
            show_timestamp=overlay.get('show_timestamp', True),
            font_size=overlay.get('font_size', 32),
            font_color=overlay.get('font_color', 'white')
        )

        logger.info(f"Loaded config: mode={self.mode.value}, cameras={len(self.cameras)}")

    def _set_defaults(self):
        """Set default configuration."""
        self.cameras = [
            CameraConfig(device='/dev/video0', name='front_cam'),
            CameraConfig(device='/dev/video2', name='rear_cam')
        ]

    def detect_cameras(self) -> List[str]:
        """Detect available video devices."""
        cameras = []
        for i in range(10):
            device = f"/dev/video{i}"
            if os.path.exists(device):
                # Check if it's a capture device
                try:
                    result = subprocess.run(
                        ['v4l2-ctl', '-d', device, '--all'],
                        capture_output=True, text=True, timeout=5
                    )
                    if 'Video Capture' in result.stdout:
                        cameras.append(device)
                        logger.info(f"Found camera: {device}")
                except Exception as e:
                    logger.debug(f"Error checking {device}: {e}")
        return cameras

    def detect_audio_device(self, video_device: str) -> Optional[str]:
        """Detect audio device associated with a video device.

        Maps video devices to their corresponding ALSA audio devices
        by matching USB device names.
        """
        try:
            # Get the video device name
            result = subprocess.run(
                ['v4l2-ctl', '-d', video_device, '--all'],
                capture_output=True, text=True, timeout=5
            )
            video_name = ""
            for line in result.stdout.split('\n'):
                if 'Card type' in line:
                    video_name = line.split(':')[1].strip().lower()
                    break

            if not video_name:
                return None

            # Read audio cards and try to match
            with open('/proc/asound/cards', 'r') as f:
                cards_info = f.read()

            # Parse audio cards
            for line in cards_info.split('\n'):
                if '[' in line and ']:' in line:
                    # Extract card number and name
                    parts = line.split()
                    if len(parts) >= 2:
                        card_num = parts[0].strip()
                        # Get the descriptive name from next part
                        card_name = line.split('- ')[1].strip().lower() if '- ' in line else ""

                        # Match by partial name (e.g., "osmo" matches "OsmoAction5pro")
                        if any(keyword in card_name for keyword in ['osmo', 'gopro', 'action']):
                            if 'osmo' in video_name.lower() or 'action' in video_name.lower():
                                audio_device = f"hw:{card_num}"
                                logger.info(f"Found audio device {audio_device} for {video_device}")
                                return audio_device

                        # Also check if video name keywords appear in audio card
                        video_keywords = video_name.replace('_', ' ').split()
                        for keyword in video_keywords:
                            if len(keyword) > 3 and keyword in card_name:
                                audio_device = f"hw:{card_num}"
                                logger.info(f"Found audio device {audio_device} for {video_device}")
                                return audio_device

            return None
        except Exception as e:
            logger.debug(f"Error detecting audio for {video_device}: {e}")
            return None

    def build_overlay_filter(self) -> str:
        """Build ffmpeg filter for overlay."""
        filters = []

        if not self.overlay.enabled:
            return ""

        # Text overlay with position
        if self.overlay.text:
            pos = getattr(self.overlay, 'text_position', 'top-center')
            pos_map = {
                'top-center': 'x=(w-text_w)/2:y=20',
                'top-left': 'x=20:y=20',
                'top-right': 'x=W-tw-20:y=20',
                'bottom-center': 'x=(w-text_w)/2:y=H-th-20',
                'bottom-left': 'x=20:y=H-th-20',
            }
            xy = pos_map.get(pos, 'x=(w-text_w)/2:y=20')
            text_filter = (
                f"drawtext=text='{self.overlay.text}':"
                f"fontsize={self.overlay.font_size}:"
                f"fontcolor={self.overlay.font_color}:"
                f"borderw=2:bordercolor=black:"
                f"{xy}"
            )
            filters.append(text_filter)

        # Timestamp (bottom right)
        if self.overlay.show_timestamp:
            timestamp_filter = (
                f"drawtext=text='%{{localtime}}':"
                f"fontsize={self.overlay.font_size}:"
                f"fontcolor={self.overlay.font_color}:"
                f"borderw=2:bordercolor=black:"
                f"x=W-tw-10:y=H-th-10"
            )
            filters.append(timestamp_filter)

        return ','.join(filters) if filters else ""

    def build_ffmpeg_cmd_standalone(self, camera: CameraConfig) -> List[str]:
        """Build ffmpeg command for standalone YouTube streaming."""
        width, height = camera.resolution.split('x')
        keyframe_frames = camera.fps * self.output.keyframe_interval

        # Get stream key for this camera
        stream_key = self.stream_keys.get(camera.name, '')
        if not stream_key:
            logger.error(f"No stream key configured for camera {camera.name}")
            return []

        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'warning',

            # Input from camera
            '-f', 'v4l2',
            '-video_size', camera.resolution,
            '-framerate', str(camera.fps),
            '-input_format', 'mjpeg',  # Most USB cameras support MJPEG
            '-i', camera.device,

            # Generate silent audio (most cameras don't have good audio)
            '-f', 'lavfi',
            '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',

            # Video encoding
            '-c:v', 'libx264',
            '-preset', self.output.preset,
            '-tune', 'zerolatency',
            '-b:v', self.output.video_bitrate,
            '-maxrate', self.output.video_bitrate,
            '-bufsize', str(int(self.output.video_bitrate.replace('k', '')) * 2) + 'k',
            '-pix_fmt', 'yuv420p',
            '-g', str(keyframe_frames),
            '-keyint_min', str(keyframe_frames),

            # Audio encoding
            '-c:a', 'aac',
            '-b:a', self.output.audio_bitrate,
            '-ar', '44100',

            # Output format
            '-f', 'flv',
            '-flvflags', 'no_duration_filesize',
        ]

        # Add overlay filter if enabled
        overlay_filter = self.build_overlay_filter()
        if overlay_filter:
            cmd.extend(['-vf', overlay_filter])

        # Output destination - each camera gets its own stream key
        output_url = f"{self.output.rtmp_url}/{stream_key}"
        cmd.append(output_url)

        return cmd

    def build_ffmpeg_cmd_coordinator(self, camera: CameraConfig) -> List[str]:
        """Build ffmpeg command for coordinator mode (stream to TRED router)."""
        keyframe_frames = camera.fps * self.output.keyframe_interval

        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'warning',

            # Input from camera
            '-f', 'v4l2',
            '-video_size', camera.resolution,
            '-framerate', str(camera.fps),
            '-input_format', 'mjpeg',
            '-i', camera.device,

            # Video encoding
            '-c:v', 'libx264',
            '-preset', self.output.preset,
            '-tune', 'zerolatency',
            '-b:v', self.output.video_bitrate,
            '-pix_fmt', 'yuv420p',
            '-g', str(keyframe_frames),
            '-keyint_min', str(keyframe_frames),

            # No audio for coordinator mode (added at coordinator)
            '-an',

            # Output to coordinator
            '-f', 'flv',
            f"{self.coordinator_url}/{camera.name}"
        ]

        return cmd

    def start_camera(self, camera: CameraConfig):
        """Start streaming from a single camera."""
        if not camera.enabled:
            logger.info(f"Camera {camera.name} is disabled, skipping")
            return

        if self.mode == Mode.STANDALONE:
            cmd = self.build_ffmpeg_cmd_standalone(camera)
        else:
            cmd = self.build_ffmpeg_cmd_coordinator(camera)

        if not cmd:
            logger.error(f"Failed to build command for camera {camera.name}")
            return

        logger.info(f"Starting camera {camera.name}: {' '.join(cmd)}")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            with self.lock:
                self.ffmpeg_processes[camera.name] = process

            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=self._monitor_process,
                args=(camera,),
                daemon=True
            )
            monitor_thread.start()

            logger.info(f"Camera {camera.name} started, PID: {process.pid}")

        except Exception as e:
            logger.error(f"Failed to start camera {camera.name}: {e}")

    def _monitor_process(self, camera: CameraConfig):
        """Monitor ffmpeg process and restart if needed."""
        while self.running:
            with self.lock:
                process = self.ffmpeg_processes.get(camera.name)

            if process is None:
                break

            returncode = process.poll()
            if returncode is not None:
                # Process died
                stderr = process.stderr.read().decode() if process.stderr else ""
                logger.warning(f"Camera {camera.name} died (code {returncode}): {stderr[-500:]}")

                if self.running:
                    # Restart after delay
                    time.sleep(5)
                    logger.info(f"Restarting camera {camera.name}")
                    self.start_camera(camera)
                break

            time.sleep(1)

    def stop_camera(self, camera_name: str):
        """Stop a specific camera stream."""
        with self.lock:
            process = self.ffmpeg_processes.get(camera_name)

        if process:
            logger.info(f"Stopping camera {camera_name}")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

            with self.lock:
                del self.ffmpeg_processes[camera_name]

    def build_ffmpeg_cmd_rotation(self, camera: CameraConfig) -> List[str]:
        """Build ffmpeg command for rotation mode - single output stream."""
        keyframe_frames = camera.fps * self.output.keyframe_interval

        if not self.stream_key:
            logger.error("No stream key configured for rotation mode")
            return []

        # Check for audio device - use config first, then auto-detect
        audio_device = camera.audio_device if camera.audio_device else self.detect_audio_device(camera.device)

        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'warning',

            # Input from camera
            '-f', 'v4l2',
            '-video_size', camera.resolution,
            '-framerate', str(camera.fps),
            '-input_format', 'mjpeg',
            '-i', camera.device,
        ]

        # Add audio input - real audio if available, otherwise silent
        if audio_device:
            logger.info(f"Using real audio from {audio_device} for camera {camera.name}")
            cmd.extend([
                '-f', 'alsa',
                '-i', audio_device,
            ])
        else:
            logger.info(f"No audio device for {camera.name}, using silent audio")
            cmd.extend([
                '-f', 'lavfi',
                '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
            ])

        cmd.extend([
            # Video encoding
            '-c:v', 'libx264',
            '-preset', self.output.preset,
            '-tune', 'zerolatency',
            '-b:v', self.output.video_bitrate,
            '-maxrate', self.output.video_bitrate,
            '-bufsize', str(int(self.output.video_bitrate.replace('k', '')) * 2) + 'k',
            '-pix_fmt', 'yuv420p',
            '-g', str(keyframe_frames),
            '-keyint_min', str(keyframe_frames),

            # Audio encoding
            '-c:a', 'aac',
            '-b:a', self.output.audio_bitrate,
            '-ar', '44100',

            # Output format
            '-f', 'flv',
            '-flvflags', 'no_duration_filesize',
        ])

        # Add overlay filter if enabled
        overlay_filter = self.build_overlay_filter()
        if overlay_filter:
            cmd.extend(['-vf', overlay_filter])

        # Single output destination
        cmd.append(f"{self.output.rtmp_url}/{self.stream_key}")

        return cmd

    def switch_camera_with_overlap(self, new_camera: CameraConfig):
        """Switch to new camera with overlap to prevent dropout."""
        old_process = None
        old_camera_name = None

        # Get current running process
        with self.lock:
            for name, proc in self.ffmpeg_processes.items():
                if proc.poll() is None:  # Still running
                    old_process = proc
                    old_camera_name = name
                    break

        # Start new camera FIRST (overlap)
        logger.info(f"Starting new camera {new_camera.name} (overlap switch)")
        cmd = self.build_ffmpeg_cmd_rotation(new_camera)
        if not cmd:
            return

        try:
            new_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Brief overlap - let new stream establish
            time.sleep(2)

            # Now stop old stream
            if old_process and old_process.poll() is None:
                logger.info(f"Stopping old camera {old_camera_name}")
                old_process.terminate()
                try:
                    old_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    old_process.kill()

                with self.lock:
                    if old_camera_name in self.ffmpeg_processes:
                        del self.ffmpeg_processes[old_camera_name]

            # Register new process
            with self.lock:
                self.ffmpeg_processes[new_camera.name] = new_process

            logger.info(f"Switched to {new_camera.name}, PID: {new_process.pid}")

        except Exception as e:
            logger.error(f"Failed to switch to {new_camera.name}: {e}")

    def check_stop_flag(self) -> bool:
        """Check if stop flag file exists."""
        return os.path.exists('/tmp/racestream_stop')

    def rotation_loop(self):
        """Main rotation loop - cycles through cameras."""
        logger.info(f"Starting rotation loop: {self.rotation_interval}s interval")

        # Clear any existing stop flag on start
        if os.path.exists('/tmp/racestream_stop'):
            os.remove('/tmp/racestream_stop')

        while self.running and not self.check_stop_flag():
            # Get enabled cameras
            enabled_cameras = [c for c in self.cameras if c.enabled]
            if not enabled_cameras:
                time.sleep(1)
                continue

            # Get current camera
            camera = enabled_cameras[self.current_camera_index % len(enabled_cameras)]

            # Switch with overlap
            self.switch_camera_with_overlap(camera)

            # Wait for rotation interval
            for _ in range(self.rotation_interval):
                if not self.running or self.check_stop_flag():
                    break
                time.sleep(1)

            # Move to next camera
            self.current_camera_index = (self.current_camera_index + 1) % len(enabled_cameras)

    def start(self):
        """Start all camera streams."""
        self.running = True

        logger.info(f"Starting RaceStream Solo in {self.mode.value} mode")

        if self.mode == Mode.STANDALONE:
            if self.rotation_enabled:
                if not self.stream_key:
                    logger.error("No stream key configured for rotation mode!")
                    return
                logger.info(f"Rotation mode: cycling cameras every {self.rotation_interval}s")
                # Start rotation in a thread
                rotation_thread = threading.Thread(target=self.rotation_loop, daemon=True)
                rotation_thread.start()
                return
            elif not self.stream_keys:
                logger.error("No stream keys configured for standalone mode!")
                return

        if self.mode == Mode.COORDINATOR and not self.coordinator_url:
            logger.error("No coordinator URL configured for coordinator mode!")
            return

        # Non-rotation mode: start all cameras
        for camera in self.cameras:
            self.start_camera(camera)
            time.sleep(1)

        logger.info(f"Started {len(self.cameras)} camera(s)")

    def stop(self):
        """Stop all camera streams."""
        self.running = False
        logger.info("Stopping all cameras")

        for camera in self.cameras:
            self.stop_camera(camera.name)

    def status(self) -> Dict:
        """Get current status."""
        with self.lock:
            active = {name: proc.poll() is None
                     for name, proc in self.ffmpeg_processes.items()}

        return {
            'mode': self.mode.value,
            'running': self.running,
            'cameras': active,
            'output': {
                'platform': self.output.platform,
                'rtmp_url': self.output.rtmp_url
            }
        }


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logger.info("Shutdown signal received")
    if 'agent' in globals():
        agent.stop()
    sys.exit(0)


def main():
    global agent

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Config path from environment or default
    config_path = os.environ.get('CONFIG_PATH', '/app/config/solo_config.yaml')

    agent = SoloAgent(config_path)

    # Auto-detect cameras if none configured
    if not agent.cameras:
        logger.info("No cameras configured, auto-detecting...")
        devices = agent.detect_cameras()
        for i, device in enumerate(devices[:2]):  # Max 2 cameras
            agent.cameras.append(CameraConfig(
                device=device,
                name=f"cam{i}"
            ))

    agent.start()

    # Keep running
    try:
        while agent.running:
            time.sleep(10)
            status = agent.status()
            logger.info(f"Status: {status}")
    except KeyboardInterrupt:
        pass
    finally:
        agent.stop()


if __name__ == '__main__':
    main()
