import subprocess
import json
import os
import pathlib
from flask import Flask, render_template, request, Response, jsonify, stream_with_context

# Ensure Deno is on PATH (required by yt-dlp for YouTube JS extraction)
deno_bin = str(pathlib.Path.home() / '.deno' / 'bin')
if deno_bin not in os.environ.get('PATH', ''):
    os.environ['PATH'] = deno_bin + os.pathsep + os.environ.get('PATH', '')

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

def get_video_info(url):
    """Fetch video metadata as JSON using yt‑dlp.
    Returns a dict on success or raises a descriptive RuntimeError on failure.
    """
    try:
        proc = subprocess.run(
            ['yt-dlp', '--extractor-args', 'youtube:player_client=android', '-j', url],
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )
        return json.loads(proc.stdout)
    except subprocess.CalledProcessError as e:
        # yt‑dlp returned a non‑zero exit code; include stderr for debugging
        raise RuntimeError(f"yt‑dlp error: {e.stderr.strip()}")
    except Exception as e:
        raise RuntimeError(f"Failed to obtain video info: {e}")

def probe_filesize(url, fmt):
    """Return filesize in bytes for a given format string, or None if unavailable."""
    try:
        result = subprocess.run(
            ['yt-dlp', '--extractor-args', 'youtube:player_client=android', '-f', fmt, '--print', 'filesize', '--skip-download', url],
            capture_output=True, text=True, check=True, timeout=20
        )
        size_str = result.stdout.strip()
        if size_str.isdigit():
            return int(size_str)
    except Exception:
        pass
    return None


def generate_presets(data, url):
    """Create download presets with accurate size (MB) for each resolution."""
    common_heights = [1080, 720, 480, 360, 240]
    presets = []
    
    # Auto best (will pick highest quality pre-merged format)
    presets.append({"label": "Best (auto)", "format": "best", "size_mb": None})
    
    # Helper: map height -> best pre-merged format for that height
    height_map = {}
    for f in data.get('formats', []):
        if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
            h = f.get('height')
            if h:
                size = f.get('filesize') or f.get('filesize_approx') or 0
                if h not in height_map or size > height_map[h]["size"]:
                    height_map[h] = {"format_id": f.get('format_id'), "size": size, "ext": f.get('ext') or 'mp4'}
                    
    # Build presets for each desired height
    for h in common_heights:
        eligible = [hh for hh in height_map.keys() if hh <= h]
        if eligible:
            best_h = max(eligible)
            fmt_str = height_map[best_h]["format_id"]
            size_bytes = height_map[best_h]["size"]
        else:
            fmt_str = f"best[height<={h}]/best"
            size_bytes = probe_filesize(url, fmt_str)
            
        size_mb = round(size_bytes / (1024 * 1024), 1) if size_bytes else None
        presets.append({"label": f"{h}p", "format": fmt_str, "size_mb": size_mb})
        
    # Audio‑only preset
    audio_formats = [f for f in data.get('formats', []) if f.get('vcodec') == 'none' and f.get('acodec') != 'none']
    if audio_formats:
        best_audio = max(audio_formats, key=lambda f: f.get('filesize') or f.get('filesize_approx') or 0)
        fmt_str = best_audio.get('format_id') or "bestaudio"
        audio_size = best_audio.get('filesize') or best_audio.get('filesize_approx')
        audio_mb = round(audio_size / (1024 * 1024), 1) if audio_size else None
        presets.append({"label": "Audio (mp3)", "format": fmt_str, "size_mb": audio_mb})
        
    return presets



@app.route('/info')
def info():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        data = get_video_info(url)
        presets = generate_presets(data, url)
        return jsonify({
            "title": data.get('title'),
            "presets": presets
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download')
def download():
    url = request.args.get('url')
    fmt = request.args.get('format', 'best')
    if not url:
        return "No URL provided", 400
    # Determine filename based on video title
    try:
        title_proc = subprocess.run(['yt-dlp', '--extractor-args', 'youtube:player_client=android', '--get-title', url], capture_output=True, text=True, check=True)
        filename = title_proc.stdout.strip()
        filename = "".join([c for c in filename if c.isalnum() or c in (' ','.','-')]).rstrip()
    except Exception:
        filename = 'video'
    # Guess extension
    if fmt.startswith('bestaudio'):
        filename += '.mp3'
    else:
        filename += '.mp4'
    # Attempt to get an approximate filesize for the Content‑Length header
    size_header = None
    try:
        probe = subprocess.run(['yt-dlp', '--extractor-args', 'youtube:player_client=android', '-f', fmt, '--print', 'filesize', '--skip-download', url], capture_output=True, text=True, check=True, timeout=20)
        size = int(probe.stdout.strip())
        size_header = str(size)
    except Exception:
        pass
    def generate():
        proc = subprocess.Popen(
            ['yt-dlp', '--extractor-args', 'youtube:player_client=android', '-f', fmt, '-o', '-', url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        while True:
            chunk = proc.stdout.read(8192)
            if not chunk:
                break
            yield chunk
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    if size_header:
        headers['Content-Length'] = size_header
    return Response(stream_with_context(generate()), headers=headers, mimetype='application/octet-stream')

if __name__ == '__main__':
    # Bind to all interfaces; use PORT env variable for cloud deployment
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
