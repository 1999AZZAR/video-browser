# app.py
from flask import Flask, render_template, send_file, abort, jsonify, request
from flask_caching import Cache
import os
import subprocess
import urllib.parse
import configparser
from PIL import Image
import io
from flask_caching import Cache
import hashlib

app = Flask(__name__)

# Read configuration
config = configparser.ConfigParser()
config.read('config.ini')

# import path from config
VIDEO_DIR = config.get('Paths', 'VIDEO_DIR')
THUMBNAIL_DIR = config.get('Paths', 'THUMBNAIL_DIR', fallback=os.path.join(VIDEO_DIR, '.thumbnails'))
SUBTITLE_EXTENSIONS = config.get('Subtitles', 'EXTENSIONS').split(',')
SHOW_HIDDEN = config.getboolean('Display', 'SHOW_HIDDEN')

# Configure caching
cache = Cache(app, config={'CACHE_TYPE': 'null'})

# Ensure thumbnail directory exists
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

def directory_contains_supported_files(path):
    """Recursively checks if a directory or its subdirectories contain supported video files."""
    for root, dirs, files in os.walk(path):
        # Filter hidden directories if SHOW_HIDDEN is False
        if not SHOW_HIDDEN:
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            files = [f for f in files if not f.startswith('.')]

        # Check for supported files
        if any(f.lower().endswith(tuple(config.get('Videos', 'EXTENSIONS').split(','))) for f in files):
            return True
    return False

@cache.memoize(300)
def get_directory_structure(path):
    structure = []
    try:
        for root, dirs, files in os.walk(path):
            if not SHOW_HIDDEN:
                dirs[:] = [d for d in dirs if not d.startswith('.')]

            rel_path = os.path.relpath(root, VIDEO_DIR)

            # Check if the current directory or any of its subdirectories contain supported files
            if rel_path != '.' and (SHOW_HIDDEN or not os.path.basename(root).startswith('.')):
                if directory_contains_supported_files(root):
                    structure.append({
                        'type': 'folder',
                        'name': os.path.basename(root),
                        'path': rel_path
                    })

            # Add supported files to the structure
            for file in files:
                if file.lower().endswith(tuple(config.get('Videos', 'EXTENSIONS').split(','))):
                    structure.append({
                        'type': 'file',
                        'name': file,
                        'path': os.path.join(rel_path, file),
                        'thumbnail': get_thumbnail_path(os.path.join(rel_path, file))
                    })

    except Exception as e:
        print(f"Error generating directory structure: {e}")
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

@cache.memoize(300)
def get_thumbnail_path(video_path):
    # Create a unique hash based on the full path of the video file
    unique_id = hashlib.md5(video_path.encode('utf-8')).hexdigest()
    thumbnail_filename = os.path.splitext(os.path.basename(video_path))[0] + '_' + unique_id + '.jpg'
    return os.path.join(THUMBNAIL_DIR, thumbnail_filename)

def generate_thumbnail(video_path):
    thumbnail_path = get_thumbnail_path(video_path)
    if not os.path.exists(thumbnail_path):
        try:
            subprocess.run([
                'ffmpeg',
                '-i', video_path,
                '-ss', '00:00:01',
                '-vframes', '1',
                '-vf', 'scale=320:-1',
                thumbnail_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            return None
    return thumbnail_path

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

        thumbnail_path = get_thumbnail_path(filename)
        return render_template('video.html', video_path=filename, subs=subs, video_title=os.path.basename(filename), thumbnail_path=thumbnail_path)
    else:
        abort(404)

@app.route('/video/<path:filename>')
def serve_file(filename):
    try:
        return send_file(os.path.join(VIDEO_DIR, filename))
    except FileNotFoundError:
        abort(404)

@app.route('/thumbnail/<path:filename>')
def serve_thumbnail(filename):
    full_path = os.path.join(VIDEO_DIR, urllib.parse.unquote_plus(filename))
    thumbnail_path = generate_thumbnail(full_path)
    if thumbnail_path:
        return send_file(thumbnail_path)
    else:
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
                        'path': video_path,
                        'thumbnail': get_thumbnail_path(video_path)
                    })
    return jsonify(related_videos)

if __name__ == '__main__':
    app.run(host=config.get('Server', 'HOST'), port=config.getint('Server', 'PORT'))
