import os
import subprocess
import urllib.parse
import configparser
import hashlib
import logging
import socket
import warnings
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, send_file, abort, jsonify, request
from flask_caching import Cache

class VideoServer:
    def __init__(self, config_path: str = 'config.ini'):
        self.app = Flask(__name__)
        self.cache = Cache(self.app, config={'CACHE_TYPE': 'null'})
        self.config = self._load_config(config_path)
        self._configure_logging()
        self._configure_routes()
        self._ensure_thumbnail_dir()
        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)  # Hardware parallelization

    def _load_config(self, config_path: str) -> configparser.ConfigParser:
        config = configparser.ConfigParser()
        config.read(config_path)
        return config

    def _configure_logging(self):
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        warnings.filterwarnings("ignore", category=UserWarning, module="flask_caching")

    def _configure_routes(self):
        self.app.add_url_rule('/', 'index', self.index)
        self.app.add_url_rule('/api/structure', 'api_structure', self.api_structure)
        self.app.add_url_rule('/play/<path:filename>', 'play_video', self.play_video)
        self.app.add_url_rule('/video/<path:filename>', 'serve_file', self.serve_file)
        self.app.add_url_rule('/thumbnail/<path:filename>', 'serve_thumbnail', self.serve_thumbnail)
        self.app.add_url_rule('/api/related-videos', 'api_related_videos', self.api_related_videos)

    def _ensure_thumbnail_dir(self):
        os.makedirs(self.thumbnail_dir, exist_ok=True)

    @property
    def video_dir(self) -> str:
        return self.config.get('Paths', 'VIDEO_DIR')

    @property
    def thumbnail_dir(self) -> str:
        return self.config.get('Paths', 'THUMBNAIL_DIR', fallback=os.path.join(self.video_dir, '.thumbnails'))

    @property
    def subtitle_extensions(self) -> List[str]:
        return self.config.get('Subtitles', 'EXTENSIONS').split(',')

    @property
    def show_hidden(self) -> bool:
        return self.config.getboolean('Display', 'SHOW_HIDDEN')

    def run(self):
        host = self.config.get('Server', 'HOST')
        port = self.config.getint('Server', 'PORT')

        print(f"Starting server on port {port}")
        ip_addresses = self._get_ip_addresses()
        for ip in ip_addresses:
            print(f"Running on http://{ip}:{port}")

        self.app.run(host=host, port=port, debug=False, use_reloader=False)

    def _get_ip_addresses(self) -> List[str]:
        try:
            hostname = socket.gethostname()
            return socket.gethostbyname_ex(hostname)[2]
        except Exception as e:
            print(f"Error getting IP addresses: {e}")
            return []

    def directory_contains_supported_files(self, path: str) -> bool:
        for root, dirs, files in os.walk(path):
            if not self.show_hidden:
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                files = [f for f in files if not f.startswith('.')]
            if any(f.lower().endswith(tuple(self.config.get('Videos', 'EXTENSIONS').split(','))) for f in files):
                return True
        return False

    def get_directory_structure(self, path: str) -> List[Dict[str, str]]:
        @self.cache.memoize(300)
        def _get_directory_structure(path: str) -> List[Dict[str, str]]:
            structure = []
            try:
                for root, dirs, files in os.walk(path):
                    if not self.show_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith('.')]

                    rel_path = os.path.relpath(root, self.video_dir)

                    if rel_path != '.' and (self.show_hidden or not os.path.basename(root).startswith('.')):
                        if self.directory_contains_supported_files(root):
                            structure.append({
                                'type': 'folder',
                                'name': os.path.basename(root),
                                'path': rel_path
                            })

                    for file in files:
                        if file.lower().endswith(tuple(self.config.get('Videos', 'EXTENSIONS').split(','))):
                            structure.append({
                                'type': 'file',
                                'name': file,
                                'path': os.path.join(rel_path, file),
                                'thumbnail': self.get_thumbnail_path(os.path.join(rel_path, file))
                            })
            except Exception as e:
                print(f"Error generating directory structure: {e}")
            return structure

        return _get_directory_structure(path)

    def extract_subtitles(self, video_path: str) -> Optional[str]:
        output_path = os.path.splitext(video_path)[0] + '.vtt'
        if not os.path.exists(output_path):
            try:
                # Utilize hardware acceleration with VAAPI, NVENC, etc.
                subprocess.run(
                    ['ffmpeg', '-hwaccel', 'auto', '-i', video_path, '-map', '0:s:0', output_path],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except subprocess.CalledProcessError:
                return None
        return output_path

    def get_thumbnail_path(self, video_path: str) -> str:
        @self.cache.memoize(300)
        def _get_thumbnail_path(video_path: str) -> str:
            unique_id = hashlib.md5(video_path.encode('utf-8')).hexdigest()
            thumbnail_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}_{unique_id}.jpg"
            return os.path.join(self.thumbnail_dir, thumbnail_filename)

        return _get_thumbnail_path(video_path)

    def generate_thumbnail(self, video_path: str) -> Optional[str]:
        thumbnail_path = self.get_thumbnail_path(video_path)
        if not os.path.exists(thumbnail_path):
            try:
                # Enable hardware acceleration
                subprocess.run([
                    'ffmpeg', '-hwaccel', 'auto', '-i', video_path,
                    '-ss', '00:00:05', '-vframes', '1', '-vf', 'scale=320:-1',
                    thumbnail_path
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                return None
        return thumbnail_path

    # Flask route handlers
    def index(self):
        return render_template('index.html')

    def api_structure(self):
        return jsonify(self.get_directory_structure(self.video_dir))

    def play_video(self, filename):
        full_path = os.path.join(self.video_dir, filename)
        if os.path.isfile(full_path):
            if filename.lower().endswith('.mkv'):
                subtitle_path = self.executor.submit(self.extract_subtitles, full_path).result()
            else:
                subtitle_path = os.path.splitext(full_path)[0] + '.vtt'

            subs = [os.path.join(os.path.dirname(filename), os.path.basename(subtitle_path))] if subtitle_path and os.path.isfile(subtitle_path) else []

            thumbnail_path = self.get_thumbnail_path(filename)
            return render_template('video.html', video_path=filename, subs=subs, video_title=os.path.basename(filename), thumbnail_path=thumbnail_path)
        else:
            abort(404)

    def serve_file(self, filename):
        try:
            return send_file(os.path.join(self.video_dir, filename))
        except FileNotFoundError:
            abort(404)

    def serve_thumbnail(self, filename):
        full_path = os.path.join(self.video_dir, urllib.parse.unquote_plus(filename))
        thumbnail_path = self.executor.submit(self.generate_thumbnail, full_path).result()
        if thumbnail_path:
            return send_file(thumbnail_path)
        else:
            abort(404)

    def api_related_videos(self):
        folder = urllib.parse.unquote(request.args.get('folder', ''))
        if folder.startswith(self.config.get('Server', 'BASE_URL')):
            folder = folder[len(self.config.get('Server', 'BASE_URL')):]
        folder_path = os.path.join(self.video_dir, folder)
        related_videos = []
        if os.path.isdir(folder_path):
            for file in os.listdir(folder_path):
                if self.show_hidden or not file.startswith('.'):
                    if file.lower().endswith(tuple(self.config.get('Videos', 'EXTENSIONS').split(','))):
                        video_path = os.path.join(folder, file)
                        related_videos.append({
                            'name': file,
                            'path': video_path,
                            'thumbnail': self.get_thumbnail_path(video_path)
                        })
        return jsonify(related_videos)

if __name__ == '__main__':
    server = VideoServer()
    server.run()
