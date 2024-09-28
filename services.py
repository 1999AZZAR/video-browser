import os
import configparser
import logging
import warnings
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
from flask import render_template, send_file, abort, jsonify, request
import urllib.parse
from utils import (
    get_ip_addresses, directory_contains_supported_files,
    get_thumbnail_path, extract_subtitles, generate_thumbnail
)

class VideoServer:
    """A class to represent the video server, handling all routes, configuration, and utility functions."""

    def __init__(self, app, cache, config_path: str = 'config.ini'):
        """Initialize the video server with the Flask app, cache, and configuration file."""
        self.app = app
        self.cache = cache
        self.config = self._load_config(config_path)
        self._configure_logging()  # Setup logging
        self._configure_routes()   # Define routes for the app
        self._ensure_thumbnail_dir()  # Ensure the thumbnail directory exists
        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)  # ThreadPoolExecutor for async tasks

    def _load_config(self, config_path: str) -> configparser.ConfigParser:
        """Load the server configuration from a .ini file."""
        config = configparser.ConfigParser()
        config.read(config_path)
        return config

    def _configure_logging(self):
        """Configure logging for the application, suppressing warnings for caching."""
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)  # Set logging level to only show errors
        warnings.filterwarnings("ignore", category=UserWarning, module="flask_caching")

    def _configure_routes(self):
        """Define the routes for the Flask application."""
        self.app.add_url_rule('/', 'index', self.index)  # Route to render index page
        self.app.add_url_rule('/api/structure', 'api_structure', self.api_structure)  # Route to get directory structure
        self.app.add_url_rule('/play/<path:filename>', 'play_video', self.play_video)  # Route to play video files
        self.app.add_url_rule('/video/<path:filename>', 'serve_file', self.serve_file)  # Route to serve video files
        self.app.add_url_rule('/thumbnail/<path:filename>', 'serve_thumbnail', self.serve_thumbnail)  # Route to serve thumbnails
        self.app.add_url_rule('/api/related-videos', 'api_related_videos', self.api_related_videos)  # Route to get related videos

    def _ensure_thumbnail_dir(self):
        """Ensure the thumbnail directory exists, create it if it doesn't."""
        os.makedirs(self.thumbnail_dir, exist_ok=True)

    @property
    def video_dir(self) -> str:
        """Return the directory path where videos are stored."""
        return self.config.get('Paths', 'VIDEO_DIR')

    @property
    def thumbnail_dir(self) -> str:
        """Return the directory path for storing thumbnails, defaults to a '.thumbnails' subdirectory in the video directory."""
        return self.config.get('Paths', 'THUMBNAIL_DIR', fallback=os.path.join(self.video_dir, '.thumbnails'))

    @property
    def subtitle_extensions(self) -> List[str]:
        """Return the list of allowed subtitle file extensions."""
        return self.config.get('Subtitles', 'EXTENSIONS').split(',')

    @property
    def show_hidden(self) -> bool:
        """Return whether or not to show hidden files in the directory listing."""
        return self.config.getboolean('Display', 'SHOW_HIDDEN')

    def run(self):
        """Run the Flask app on the host and port specified in the configuration."""
        host = self.config.get('Server', 'HOST')
        port = self.config.getint('Server', 'PORT')

        print(f"Starting server on port {port}")
        ip_addresses = get_ip_addresses()  # Get the server IP addresses
        for ip in ip_addresses:
            print(f"Running on http://{ip}:{port}")

        self.app.run(host=host, port=port, debug=False, use_reloader=False)  # Start the Flask app

    def get_directory_structure(self, path: str) -> List[Dict[str, str]]:
        """Return the structure of the directory, including folders and supported video files."""
        @self.cache.memoize(300)  # Cache the directory structure for 300 seconds
        def _get_directory_structure(path: str) -> List[Dict[str, str]]:
            structure = []
            try:
                # Traverse the directory and generate its structure
                for root, dirs, files in os.walk(path):
                    if not self.show_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith('.')]  # Filter hidden directories

                    rel_path = os.path.relpath(root, self.video_dir)

                    # If the current directory is not the base directory, add it to the structure
                    if rel_path != '.' and (self.show_hidden or not os.path.basename(root).startswith('.')):
                        if directory_contains_supported_files(root, self.config.get('Videos', 'EXTENSIONS').split(','), self.show_hidden):
                            structure.append({
                                'type': 'folder',
                                'name': os.path.basename(root),
                                'path': rel_path
                            })

                    # Add video files to the structure
                    for file in files:
                        if file.lower().endswith(tuple(self.config.get('Videos', 'EXTENSIONS').split(','))):
                            structure.append({
                                'type': 'file',
                                'name': file,
                                'path': os.path.join(rel_path, file),
                                'thumbnail': get_thumbnail_path(os.path.join(rel_path, file), self.thumbnail_dir)
                            })
            except Exception as e:
                print(f"Error generating directory structure: {e}")  # Handle any errors during directory walk
            return structure

        return _get_directory_structure(path)  # Return the cached structure

    # Flask route handlers
    def index(self):
        """Render the index page."""
        return render_template('index.html')

    def api_structure(self):
        """Return the directory structure as a JSON response."""
        return jsonify(self.get_directory_structure(self.video_dir))

    def play_video(self, filename):
        """Render the video player page with the video and subtitles."""
        full_path = os.path.join(self.video_dir, filename)
        if os.path.isfile(full_path):
            # Extract subtitles for MKV files or use the VTT file
            if filename.lower().endswith('.mkv'):
                subtitle_path = self.executor.submit(extract_subtitles, full_path).result()
            else:
                subtitle_path = os.path.splitext(full_path)[0] + '.vtt'

            # Prepare the subtitle and thumbnail paths
            subs = [os.path.join(os.path.dirname(filename), os.path.basename(subtitle_path))] if subtitle_path and os.path.isfile(subtitle_path) else []
            thumbnail_path = get_thumbnail_path(filename, self.thumbnail_dir)

            return render_template('video.html', video_path=filename, subs=subs, video_title=os.path.basename(filename), thumbnail_path=thumbnail_path)
        else:
            abort(404)  # Return a 404 if the video file is not found

    def serve_file(self, filename):
        """Serve the requested video file."""
        try:
            return send_file(os.path.join(self.video_dir, filename))
        except FileNotFoundError:
            abort(404)  # Return a 404 if the file is not found

    def serve_thumbnail(self, filename):
        """Serve the thumbnail image for the requested video."""
        full_path = os.path.join(self.video_dir, urllib.parse.unquote_plus(filename))
        thumbnail_path = get_thumbnail_path(full_path, self.thumbnail_dir)
        thumbnail_path = self.executor.submit(generate_thumbnail, full_path, thumbnail_path).result()
        if thumbnail_path:
            return send_file(thumbnail_path)  # Send the generated thumbnail
        else:
            abort(404)  # Return a 404 if the thumbnail could not be generated

    def api_related_videos(self):
        """Return a list of related videos in the specified folder."""
        folder = urllib.parse.unquote(request.args.get('folder', ''))
        if folder.startswith(self.config.get('Server', 'BASE_URL')):
            folder = folder[len(self.config.get('Server', 'BASE_URL')):]  # Remove base URL prefix
        folder_path = os.path.join(self.video_dir, folder)
        related_videos = []

        # Check if the folder exists and list related video files
        if os.path.isdir(folder_path):
            for file in os.listdir(folder_path):
                if self.show_hidden or not file.startswith('.'):
                    if file.lower().endswith(tuple(self.config.get('Videos', 'EXTENSIONS').split(','))):
                        video_path = os.path.join(folder, file)
                        related_videos.append({
                            'name': file,
                            'path': video_path,
                            'thumbnail': get_thumbnail_path(video_path, self.thumbnail_dir)
                        })
        return jsonify(related_videos)  # Return the related videos as a JSON response
