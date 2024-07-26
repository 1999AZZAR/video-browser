# app.py
from flask import Flask, render_template, send_file, abort, jsonify, request
from flask_caching import Cache
import os
import subprocess
import urllib.parse
import configparser

app = Flask(__name__)

# Read configuration
config = configparser.ConfigParser()
config.read('config.ini')

# Configure caching
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

VIDEO_DIR = config.get('Paths', 'VIDEO_DIR')
SUBTITLE_EXTENSIONS = config.get('Subtitles', 'EXTENSIONS').split(',')
SHOW_HIDDEN = config.getboolean('Display', 'SHOW_HIDDEN')

@cache.memoize(300)
def get_directory_structure(path):
    structure = []
    try:
        for root, dirs, files in os.walk(path):
            if not SHOW_HIDDEN:
                # Remove hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]

            rel_path = os.path.relpath(root, VIDEO_DIR)
            if rel_path != '.':
                if SHOW_HIDDEN or not os.path.basename(root).startswith('.'):
                    structure.append({
                        'type': 'folder',
                        'name': os.path.basename(root),
                        'path': rel_path
                    })
            for file in files:
                if SHOW_HIDDEN or not file.startswith('.'):
                    if file.lower().endswith(tuple(config.get('Videos', 'EXTENSIONS').split(','))):
                        structure.append({
                            'type': 'file',
                            'name': file,
                            'path': os.path.join(rel_path, file)
                        })
    except Exception:
        pass
    return structure

def extract_subtitles(video_path):
    output_path = os.path.splitext(video_path)[0] + '.vtt'
    if not os.path.exists(output_path):
        try:
            subprocess.run(
                ['ffmpeg', '-i', video_path, '-map', '0:s:0', output_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            return None
    return output_path

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/structure')
@cache.cached(timeout=300)
def api_structure():
    return jsonify(get_directory_structure(VIDEO_DIR))

@app.route('/play/<path:filename>')
def play_video(filename):
    full_path = os.path.join(VIDEO_DIR, filename)
    if os.path.isfile(full_path):
        if filename.lower().endswith('.mkv'):
            subtitle_path = extract_subtitles(full_path)
        else:
            subtitle_path = os.path.splitext(full_path)[0] + '.vtt'

        if subtitle_path and os.path.isfile(subtitle_path):
            subs = [os.path.join(os.path.dirname(filename), os.path.basename(subtitle_path))]
        else:
            subs = []

        return render_template('video.html', video_path=filename, subs=subs, video_title=os.path.basename(filename))
    else:
        abort(404)

@app.route('/video/<path:filename>')
def serve_file(filename):
    try:
        return send_file(os.path.join(VIDEO_DIR, filename))
    except FileNotFoundError:
        abort(404)

@app.route('/api/related-videos')
def api_related_videos():
    folder = urllib.parse.unquote(request.args.get('folder', ''))
    if folder.startswith(config.get('Server', 'BASE_URL')):
        folder = folder[len(config.get('Server', 'BASE_URL')):]
    folder_path = os.path.join(VIDEO_DIR, folder)
    related_videos = []
    if os.path.isdir(folder_path):
        for file in os.listdir(folder_path):
            if SHOW_HIDDEN or not file.startswith('.'):
                if file.lower().endswith(tuple(config.get('Videos', 'EXTENSIONS').split(','))):
                    video_path = os.path.join(folder, file)
                    related_videos.append({
                        'name': file,
                        'path': video_path
                    })
    return jsonify(related_videos)

if __name__ == '__main__':
    app.run(host=config.get('Server', 'HOST'), port=config.getint('Server', 'PORT'))
