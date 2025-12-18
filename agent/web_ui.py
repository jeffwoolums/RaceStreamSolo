#!/usr/bin/env python3
"""
RaceStream Solo Web UI
Lightweight Flask-based configuration and control interface.
"""

import os
import yaml
import subprocess
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from pathlib import Path
from camera_manager import CameraManager

app = Flask(__name__)
camera_manager = CameraManager()

CONFIG_PATH = os.environ.get('CONFIG_PATH', '/app/config/solo_config.yaml')

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>RaceStream Solo</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {% if auto_refresh %}
    <meta http-equiv="refresh" content="3;url=/">
    {% endif %}
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            margin: 0;
            padding: 20px;
        }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { color: #00d4ff; margin-bottom: 5px; }
        .subtitle { color: #888; margin-bottom: 30px; }
        .card {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #0f3460;
        }
        .card h2 { margin-top: 0; color: #00d4ff; font-size: 1.2em; }
        .status {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
        }
        .status.live { background: #00c853; color: #000; }
        .status.offline { background: #ff5252; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; color: #aaa; font-size: 0.9em; }
        input, select {
            width: 100%;
            padding: 10px;
            border: 1px solid #0f3460;
            border-radius: 5px;
            background: #1a1a2e;
            color: #fff;
            font-size: 1em;
        }
        input:focus, select:focus { outline: none; border-color: #00d4ff; }
        .btn {
            padding: 12px 25px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1em;
            font-weight: bold;
            margin-right: 10px;
            margin-bottom: 10px;
        }
        .btn-primary { background: #00d4ff; color: #000; }
        .btn-danger { background: #ff5252; color: #fff; }
        .btn-success { background: #00c853; color: #000; }
        .btn-secondary { background: #444; color: #fff; }
        .btn:hover { opacity: 0.9; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
        .camera-card {
            background: #0f3460;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .camera-card h3 { margin: 0 0 10px 0; }
        .camera-status { font-size: 0.9em; color: #aaa; }
        .toggle {
            position: relative;
            display: inline-block;
            width: 50px;
            height: 26px;
        }
        .toggle input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: #444;
            transition: .3s;
            border-radius: 26px;
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 20px;
            width: 20px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: .3s;
            border-radius: 50%;
        }
        input:checked + .slider { background-color: #00d4ff; }
        input:checked + .slider:before { transform: translateX(24px); }
        .inline-toggle { display: flex; align-items: center; justify-content: space-between; }
        .message {
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .message.success { background: #00c85333; border: 1px solid #00c853; }
        .message.error { background: #ff525233; border: 1px solid #ff5252; }
        .current-cam { color: #00d4ff; font-weight: bold; }
        .log-viewer {
            background: #0a0a1a;
            border: 1px solid #0f3460;
            border-radius: 5px;
            padding: 15px;
            font-family: monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
            color: #aaa;
        }
        .log-viewer .error { color: #ff5252; }
        .log-viewer .warning { color: #ffc107; }
        .log-viewer .info { color: #00d4ff; }
        .detected-cam {
            background: #0f3460;
            padding: 10px 15px;
            border-radius: 8px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .detected-cam .cam-info { flex: 1; }
        .detected-cam .cam-name { font-weight: bold; color: #00d4ff; }
        .detected-cam .cam-detail { font-size: 0.85em; color: #888; margin-top: 3px; }
        .btn-sm { padding: 6px 12px; font-size: 0.85em; }
    </style>
</head>
<body>
    <div class="container">
        <h1>RaceStream Solo</h1>
        <p class="subtitle">Standalone Streaming Device</p>

        {% if message %}
        <div class="message {{ message_type }}">{{ message }}</div>
        {% endif %}

        <!-- Status Card -->
        <div class="card">
            <h2>Stream Status</h2>
            <p>
                <span class="status {{ 'live' if status.running else 'offline' }}">
                    {{ 'LIVE' if status.running else 'OFFLINE' }}
                </span>
                {% if status.running and status.current_camera %}
                <span style="margin-left: 15px;">Current: <span class="current-cam">{{ status.current_camera }}</span></span>
                {% endif %}
            </p>
            <div style="margin-top: 15px;">
                {% if status.running %}
                <form action="/stop" method="post" style="display: inline;">
                    <button type="submit" class="btn btn-danger">Stop Stream</button>
                </form>
                {% else %}
                <form action="/start" method="post" style="display: inline;">
                    <button type="submit" class="btn btn-success">Start Stream</button>
                </form>
                {% endif %}
                <form action="/restart" method="post" style="display: inline;">
                    <button type="submit" class="btn btn-secondary">Restart</button>
                </form>
                {% if config.youtube_url %}
                <a href="{{ config.youtube_url }}" target="_blank" class="btn btn-primary" style="text-decoration: none; display: inline-block;">Watch Live</a>
                {% endif %}
            </div>
        </div>

        <!-- Cameras Card -->
        <div class="card">
            <h2>Cameras</h2>
            <div class="grid">
                {% for cam in config.cameras %}
                <div class="camera-card">
                    <h3>{{ cam.name }}</h3>
                    <p class="camera-status">{{ cam.device }}</p>
                    <p class="camera-status">{{ cam.resolution }} @ {{ cam.fps }}fps</p>
                    <p style="color: {{ '#00c853' if cam.enabled else '#ff5252' }}">
                        {{ 'Enabled' if cam.enabled else 'Disabled' }}
                    </p>
                </div>
                {% endfor %}
            </div>
        </div>

        <!-- Discover Cameras Card -->
        <div class="card">
            <h2>Discover Cameras</h2>
            <p style="color: #aaa; margin-bottom: 15px;">Scan for connected USB cameras</p>
            <form action="/discover" method="post" style="margin-bottom: 15px;">
                <button type="submit" class="btn btn-primary">Scan for Cameras</button>
            </form>
            {% if detected_cameras %}
            <div id="detected-cameras">
                {% for cam in detected_cameras %}
                <div class="detected-cam">
                    <div class="cam-info">
                        <div class="cam-name">{{ cam.model }}</div>
                        <div class="cam-detail">{{ cam.device }} | {{ cam.best_resolution() }} | {{ 'MJPEG' if cam.supports_mjpeg() else 'YUYV' }}</div>
                        <div class="cam-detail">Formats: {{ cam.formats | join(', ') }}</div>
                    </div>
                    <form action="/add_camera" method="post" style="margin: 0;">
                        <input type="hidden" name="device" value="{{ cam.device }}">
                        <input type="hidden" name="model" value="{{ cam.model }}">
                        <input type="hidden" name="resolution" value="{{ cam.best_resolution() }}">
                        <button type="submit" class="btn btn-success btn-sm">Add to Config</button>
                    </form>
                </div>
                {% endfor %}
            </div>
            {% endif %}
        </div>

        <!-- Log Viewer Card -->
        <div class="card">
            <h2>Agent Log</h2>
            <div style="margin-bottom: 10px;">
                <a href="/logs" class="btn btn-secondary btn-sm">Refresh</a>
                <a href="/logs/clear" class="btn btn-danger btn-sm">Clear Log</a>
            </div>
            <div class="log-viewer">{{ log_content if log_content else 'No log data available. Start the stream to generate logs.' }}</div>
        </div>

        <!-- Configuration Card -->
        <div class="card">
            <h2>Configuration</h2>
            <form action="/save" method="post">

                <div class="form-group inline-toggle">
                    <label style="margin: 0;">Rotation Mode</label>
                    <label class="toggle">
                        <input type="checkbox" name="rotation_enabled" {{ 'checked' if config.rotation.enabled }}>
                        <span class="slider"></span>
                    </label>
                </div>

                <div class="form-group">
                    <label>Rotation Interval (seconds)</label>
                    <input type="number" name="rotation_interval" value="{{ config.rotation.interval }}" min="5" max="300">
                </div>

                <div class="form-group">
                    <label>Stream Key</label>
                    <input type="text" name="stream_key" value="{{ config.rotation.stream_key }}" placeholder="YouTube stream key">
                </div>

                <div class="form-group">
                    <label>RTMP URL</label>
                    <input type="text" name="rtmp_url" value="{{ config.output.rtmp_url }}">
                </div>

                <hr style="border-color: #0f3460; margin: 20px 0;">

                <div class="form-group inline-toggle">
                    <label style="margin: 0;">Overlay</label>
                    <label class="toggle">
                        <input type="checkbox" name="overlay_enabled" {{ 'checked' if config.overlay.enabled }}>
                        <span class="slider"></span>
                    </label>
                </div>

                <div class="form-group">
                    <label>Overlay Text</label>
                    <input type="text" name="overlay_text" value="{{ config.overlay.text }}">
                </div>

                <div class="grid">
                    <div class="form-group">
                        <label>Font Size</label>
                        <select name="font_size">
                            <option value="24" {{ 'selected' if config.overlay.font_size == 24 }}>Small (24)</option>
                            <option value="32" {{ 'selected' if config.overlay.font_size == 32 }}>Medium (32)</option>
                            <option value="48" {{ 'selected' if config.overlay.font_size == 48 }}>Large (48)</option>
                            <option value="64" {{ 'selected' if config.overlay.font_size == 64 }}>Extra Large (64)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Text Position</label>
                        <select name="text_position">
                            <option value="top-center" {{ 'selected' if config.overlay.text_position == 'top-center' }}>Top Center</option>
                            <option value="top-left" {{ 'selected' if config.overlay.text_position == 'top-left' }}>Top Left</option>
                            <option value="top-right" {{ 'selected' if config.overlay.text_position == 'top-right' }}>Top Right</option>
                            <option value="bottom-center" {{ 'selected' if config.overlay.text_position == 'bottom-center' }}>Bottom Center</option>
                            <option value="bottom-left" {{ 'selected' if config.overlay.text_position == 'bottom-left' }}>Bottom Left</option>
                        </select>
                    </div>
                </div>

                <div class="form-group inline-toggle">
                    <label style="margin: 0;">Show Timestamp</label>
                    <label class="toggle">
                        <input type="checkbox" name="show_timestamp" {{ 'checked' if config.overlay.show_timestamp }}>
                        <span class="slider"></span>
                    </label>
                </div>

                <hr style="border-color: #0f3460; margin: 20px 0;">

                <div class="grid">
                    <div class="form-group">
                        <label>Video Bitrate</label>
                        <select name="video_bitrate">
                            <option value="2500k" {{ 'selected' if config.output.video_bitrate == '2500k' }}>2500k (720p)</option>
                            <option value="4500k" {{ 'selected' if config.output.video_bitrate == '4500k' }}>4500k (1080p)</option>
                            <option value="6000k" {{ 'selected' if config.output.video_bitrate == '6000k' }}>6000k (1080p HQ)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Encoding Preset</label>
                        <select name="preset">
                            <option value="ultrafast" {{ 'selected' if config.output.preset == 'ultrafast' }}>Ultra Fast</option>
                            <option value="superfast" {{ 'selected' if config.output.preset == 'superfast' }}>Super Fast</option>
                            <option value="veryfast" {{ 'selected' if config.output.preset == 'veryfast' }}>Very Fast</option>
                            <option value="fast" {{ 'selected' if config.output.preset == 'fast' }}>Fast</option>
                        </select>
                    </div>
                </div>

                <button type="submit" class="btn btn-primary">Save & Restart</button>
            </form>
        </div>

        <!-- Manual Switch Card -->
        {% if status.running and config.rotation.enabled %}
        <div class="card">
            <h2>Manual Switch</h2>
            <p style="color: #aaa; margin-bottom: 15px;">Force switch to a specific camera</p>
            <form action="/switch" method="post">
                {% for cam in config.cameras %}
                <button type="submit" name="camera" value="{{ cam.name }}" class="btn btn-secondary">
                    Switch to {{ cam.name }}
                </button>
                {% endfor %}
            </form>
        </div>
        {% endif %}

    </div>
</body>
</html>
'''

def load_config():
    """Load configuration from YAML file."""
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    except Exception as e:
        return {
            'mode': 'standalone',
            'cameras': [],
            'rotation': {'enabled': True, 'interval': 15, 'stream_key': ''},
            'output': {'rtmp_url': 'rtmp://a.rtmp.youtube.com/live2', 'video_bitrate': '4500k', 'preset': 'ultrafast'},
            'overlay': {'enabled': False, 'text': '', 'show_timestamp': True}
        }

def save_config(config):
    """Save configuration to YAML file."""
    with open(CONFIG_PATH, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

def get_stream_status():
    """Get current streaming status."""
    try:
        # Check if ffmpeg is running (more reliable than checking for agent)
        result = subprocess.run(
            ['pgrep', '-f', 'ffmpeg'],
            capture_output=True
        )
        running = result.returncode == 0

        # Try to get current camera from process
        current_camera = None
        if running:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True, text=True
            )
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if 'ffmpeg' in line and 'rtmp' in line:
                        if '/dev/video0' in line:
                            current_camera = 'front_cam'
                        elif '/dev/video2' in line:
                            current_camera = 'rear_cam'
                        break

        return {'running': running, 'current_camera': current_camera}
    except:
        return {'running': False, 'current_camera': None}

def get_log_content(lines=100):
    """Get the last N lines from the agent log."""
    log_path = '/app/logs/agent.log'
    try:
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
    except Exception as e:
        return f"Error reading log: {e}"
    return ""

@app.route('/')
def index():
    config = load_config()
    status = get_stream_status()
    message = request.args.get('message')
    message_type = request.args.get('type', 'success')
    log_content = get_log_content()
    detected_cameras = request.args.get('show_cameras') == '1'
    cameras = camera_manager.detect_cameras() if detected_cameras else []
    auto_refresh = request.args.get('refresh') == '1'
    return render_template_string(HTML_TEMPLATE, config=config, status=status, message=message, message_type=message_type, log_content=log_content, detected_cameras=cameras, auto_refresh=auto_refresh)

@app.route('/save', methods=['POST'])
def save():
    config = load_config()

    # Update rotation settings
    config['rotation']['enabled'] = 'rotation_enabled' in request.form
    config['rotation']['interval'] = int(request.form.get('rotation_interval', 15))
    config['rotation']['stream_key'] = request.form.get('stream_key', '')

    # Update output settings
    config['output']['rtmp_url'] = request.form.get('rtmp_url', 'rtmp://a.rtmp.youtube.com/live2')
    config['output']['video_bitrate'] = request.form.get('video_bitrate', '4500k')
    config['output']['preset'] = request.form.get('preset', 'ultrafast')

    # Update overlay settings
    config['overlay']['enabled'] = 'overlay_enabled' in request.form
    config['overlay']['text'] = request.form.get('overlay_text', '')
    config['overlay']['font_size'] = int(request.form.get('font_size', 32))
    config['overlay']['text_position'] = request.form.get('text_position', 'top-center')
    config['overlay']['show_timestamp'] = 'show_timestamp' in request.form

    save_config(config)

    # Restart the stream
    subprocess.run(['pkill', '-9', '-f', 'ffmpeg'], capture_output=True)
    subprocess.run(['pkill', '-9', '-f', 'solo_agent.py'], capture_output=True)
    import time
    time.sleep(1)
    subprocess.Popen(
        ['python3', '/app/agent/solo_agent.py'],
        stdout=open('/app/logs/agent.log', 'a'),
        stderr=subprocess.STDOUT,
        start_new_session=True
    )

    return redirect(url_for('index', message='Configuration saved! Restarting stream...', type='success', refresh='1'))

@app.route('/start', methods=['POST'])
def start():
    # Clear stop flag
    if os.path.exists('/tmp/racestream_stop'):
        os.remove('/tmp/racestream_stop')
    # Kill any existing ffmpeg
    subprocess.run(['pkill', '-9', '-f', 'ffmpeg'], capture_output=True)
    import time
    time.sleep(1)
    # Start the agent
    subprocess.Popen(
        ['python3', '/app/agent/solo_agent.py'],
        stdout=open('/app/logs/agent.log', 'a'),
        stderr=subprocess.STDOUT,
        start_new_session=True
    )
    return redirect(url_for('index', message='Stream starting...', type='success', refresh='1'))

@app.route('/stop', methods=['POST'])
def stop():
    # Create stop flag to signal agent to stop
    Path('/tmp/racestream_stop').touch()
    import time
    time.sleep(1)
    # Kill any running ffmpeg processes
    subprocess.run(['pkill', '-9', '-f', 'ffmpeg'], capture_output=True)
    return redirect(url_for('index', message='Stream stopped', type='success'))

@app.route('/restart', methods=['POST'])
def restart():
    # Create stop flag and kill ffmpeg
    Path('/tmp/racestream_stop').touch()
    subprocess.run(['pkill', '-9', '-f', 'ffmpeg'], capture_output=True)
    import time
    time.sleep(1)
    # Remove stop flag and start fresh
    if os.path.exists('/tmp/racestream_stop'):
        os.remove('/tmp/racestream_stop')
    subprocess.Popen(
        ['python3', '/app/agent/solo_agent.py'],
        stdout=open('/app/logs/agent.log', 'a'),
        stderr=subprocess.STDOUT,
        start_new_session=True
    )
    return redirect(url_for('index', message='Stream restarting...', type='success', refresh='1'))

@app.route('/switch', methods=['POST'])
def switch():
    camera = request.form.get('camera')
    # TODO: Implement manual switch via IPC
    return redirect(url_for('index', message=f'Switching to {camera}...', type='success'))

@app.route('/discover', methods=['POST'])
def discover():
    return redirect(url_for('index', show_cameras='1', message='Cameras scanned!', type='success'))

@app.route('/add_camera', methods=['POST'])
def add_camera():
    device = request.form.get('device')
    model = request.form.get('model')
    resolution = request.form.get('resolution', '1920x1080')

    config = load_config()

    # Check if camera already exists
    existing_devices = [c['device'] for c in config.get('cameras', [])]
    if device in existing_devices:
        return redirect(url_for('index', message=f'Camera {device} already in config', type='error'))

    # Generate a name
    cam_num = len(config.get('cameras', []))
    name = f"cam{cam_num}"

    # Add camera to config
    if 'cameras' not in config:
        config['cameras'] = []

    config['cameras'].append({
        'device': device,
        'name': name,
        'resolution': resolution,
        'fps': 30,
        'enabled': True
    })

    save_config(config)
    return redirect(url_for('index', message=f'Added {model} as {name}', type='success'))

@app.route('/logs')
def logs():
    config = load_config()
    status = get_stream_status()
    log_content = get_log_content(200)  # More lines for dedicated view
    return render_template_string(HTML_TEMPLATE, config=config, status=status, log_content=log_content, detected_cameras=[])

@app.route('/logs/clear')
def clear_logs():
    log_path = '/app/logs/agent.log'
    try:
        with open(log_path, 'w') as f:
            f.write('')
        return redirect(url_for('index', message='Log cleared', type='success'))
    except Exception as e:
        return redirect(url_for('index', message=f'Error clearing log: {e}', type='error'))

@app.route('/api/status')
def api_status():
    return jsonify(get_stream_status())

@app.route('/api/config')
def api_config():
    return jsonify(load_config())


def start_agent():
    """Start the streaming agent."""
    # Clear any stop flag
    if os.path.exists('/tmp/racestream_stop'):
        os.remove('/tmp/racestream_stop')
    subprocess.Popen(
        ['python3', '/app/agent/solo_agent.py'],
        stdout=open('/app/logs/agent.log', 'a'),
        stderr=subprocess.STDOUT,
        start_new_session=True
    )

if __name__ == '__main__':
    # Auto-start the agent when web UI starts
    start_agent()
    app.run(host='0.0.0.0', port=8080, debug=False)
