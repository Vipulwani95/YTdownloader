import os
import json
import urllib.request
from flask import Flask, render_template, request, jsonify, redirect

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

def get_cobalt_url(youtube_url, is_audio=False):
    instances = [
        "https://co.wuk.sh/api/json",
        "https://cobalt.qewertyy.dev/api/json"
    ]
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    payload = {
        "url": youtube_url,
        "vQuality": "1080",
        "isAudioOnly": is_audio
    }
    data = json.dumps(payload).encode('utf-8')
    
    last_err = ""
    for api_url in instances:
        req = urllib.request.Request(api_url, data=data, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                if 'url' in res_data:
                    return res_data['url']
                elif res_data.get('status') == 'error':
                    last_err = res_data.get('text', 'Unknown error')
        except Exception as e:
            last_err = str(e)
            continue
            
    raise RuntimeError(f"All ad-free API servers are currently busy. Try again later. ({last_err})")

@app.route('/info')
def info():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # Return instantaneous presets (we will fetch the actual link on download click)
    presets = [
        {"label": "Video (1080p Ad-Free)", "format": "video", "size_mb": "Auto"},
        {"label": "Audio (MP3 Ad-Free)", "format": "audio", "size_mb": "Auto"}
    ]
    return jsonify({
        "title": "Download Ready!",
        "presets": presets
    })

@app.route('/download')
def download():
    url = request.args.get('url')
    fmt = request.args.get('format', 'video')
    if not url:
        return "No URL provided", 400
    
    try:
        is_audio = (fmt == 'audio')
        download_url = get_cobalt_url(url, is_audio=is_audio)
        # Redirect the user's browser directly to the clean video/audio file
        return redirect(download_url)
    except Exception as e:
        return f"Download failed: {e}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
