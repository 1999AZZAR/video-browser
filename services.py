import os
import configparser
import logging
import warnings
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
from flask import render_template, send_file, abort, jsonify, request
import urllib.parse
from utils import (
    get_ip_addresses,
    directory_contains_supported_files,
    get_thumbnail_path,
    extract_subtitles,
    generate_thumbnail,
)


class VideoServer:
    def __init__(self, app, cache, config_path: str = "config.ini"):
        self.app = app
        self.cache = cache
        self.config = self._load_config(config_path)
        self._configure_logging()
        self._configure_routes()
        self._ensure_thumbnail_dir()
        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

    def _load_config(self, config_path: str) -> configparser.ConfigParser:
        config = configparser.ConfigParser()
        if not config.read(config_path):
            logging.error(f"Failed to read configuration file: {config_path}")
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        return config

    def _configure_logging(self):
        logging.getLogger("werkzeug").setLevel(
            logging.CRITICAL
        )  # Suppress Werkzeug logs
        warnings.filterwarnings("ignore", category=UserWarning, module="flask_caching")

    def _configure_routes(self):
        self.app.add_url_rule("/", "index", self.index)
        self.app.add_url_rule("/api/structure", "api_structure", self.api_structure)
        self.app.add_url_rule("/play/<path:filename>", "play_video", self.play_video)
        self.app.add_url_rule("/video/<path:filename>", "serve_file", self.serve_file)
        self.app.add_url_rule(
            "/thumbnail/<path:filename>", "serve_thumbnail", self.serve_thumbnail
        )
        self.app.add_url_rule(
            "/api/related-videos", "api_related_videos", self.api_related_videos
        )

    def _ensure_thumbnail_dir(self):
        try:
            os.makedirs(self.thumbnail_dir, exist_ok=True)
        except OSError as e:
            logging.error(f"Failed to create thumbnail directory: {e}")
            raise

    @property
    def video_dir(self) -> str:
        return self.config.get("Paths", "VIDEO_DIR")

    @property
    def thumbnail_dir(self) -> str:
        return self.config.get(
            "Paths",
            "THUMBNAIL_DIR",
            fallback=os.path.join(self.video_dir, ".thumbnails"),
        )

    @property
    def subtitle_extensions(self) -> List[str]:
        return self.config.get("Subtitles", "EXTENSIONS").split(",")

    @property
    def show_hidden(self) -> bool:
        return self.config.getboolean("Display", "SHOW_HIDDEN")

    def run(self):
        host = self.config.get("Server", "HOST")
        port = self.config.getint("Server", "PORT")

        logging.info(f"Starting server on port {port}")
        ip_addresses = get_ip_addresses()
        for ip in ip_addresses:
            logging.info(f"Running on http://{ip}:{port}")

        self.app.run(host=host, port=port, debug=False, use_reloader=False)

    def get_directory_structure(self, path: str) -> List[Dict[str, str]]:
        @self.cache.memoize(300)
        def _get_directory_structure(path: str) -> List[Dict[str, str]]:
            structure = []
            try:
                for root, dirs, files in os.walk(path):
                    if not self.show_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith(".")]

                    rel_path = os.path.relpath(root, self.video_dir)

                    if rel_path != "." and (
                        self.show_hidden or not os.path.basename(root).startswith(".")
                    ):
                        if directory_contains_supported_files(
                            root,
                            self.config.get("Videos", "EXTENSIONS").split(","),
                            self.show_hidden,
                        ):
                            structure.append(
                                {
                                    "type": "folder",
                                    "name": os.path.basename(root),
                                    "path": rel_path,
                                }
                            )

                    for file in files:
                        if file.lower().endswith(
                            tuple(self.config.get("Videos", "EXTENSIONS").split(","))
                        ):
                            structure.append(
                                {
                                    "type": "file",
                                    "name": file,
                                    "path": os.path.join(rel_path, file),
                                    "thumbnail": get_thumbnail_path(
                                        os.path.join(rel_path, file), self.thumbnail_dir
                                    ),
                                }
                            )
            except Exception as e:
                logging.error(f"Error generating directory structure: {e}")
            return structure

        return _get_directory_structure(path)

    def index(self):
        return render_template("index.html")

    def api_structure(self):
        return jsonify(self.get_directory_structure(self.video_dir))

    def play_video(self, filename):
        full_path = os.path.join(self.video_dir, filename)
        if os.path.isfile(full_path):
            if filename.lower().endswith(".mkv"):
                subtitle_path = self.executor.submit(
                    extract_subtitles, full_path
                ).result()
            else:
                subtitle_path = os.path.splitext(full_path)[0] + ".vtt"

            subs = (
                [
                    os.path.join(
                        os.path.dirname(filename), os.path.basename(subtitle_path)
                    )
                ]
                if subtitle_path and os.path.isfile(subtitle_path)
                else []
            )
            thumbnail_path = get_thumbnail_path(filename, self.thumbnail_dir)

            return render_template(
                "video.html",
                video_path=filename,
                subs=subs,
                video_title=os.path.basename(filename),
                thumbnail_path=thumbnail_path,
            )
        else:
            abort(404)

    def serve_file(self, filename):
        try:
            return send_file(os.path.join(self.video_dir, filename))
        except FileNotFoundError:
            abort(404)

    def serve_thumbnail(self, filename):
        full_path = os.path.join(self.video_dir, urllib.parse.unquote_plus(filename))
        thumbnail_path = get_thumbnail_path(full_path, self.thumbnail_dir)
        thumbnail_path = self.executor.submit(
            generate_thumbnail, full_path, thumbnail_path
        ).result()
        if thumbnail_path:
            return send_file(thumbnail_path)
        else:
            abort(404)

    def api_related_videos(self):
        folder = urllib.parse.unquote(request.args.get("folder", ""))
        if folder.startswith(self.config.get("Server", "BASE_URL")):
            folder = folder[len(self.config.get("Server", "BASE_URL")) :]
        folder_path = os.path.join(self.video_dir, folder)
        related_videos = []

        if os.path.isdir(folder_path):
            for file in os.listdir(folder_path):
                if self.show_hidden or not file.startswith("."):
                    if file.lower().endswith(
                        tuple(self.config.get("Videos", "EXTENSIONS").split(","))
                    ):
                        video_path = os.path.join(folder, file)
                        related_videos.append(
                            {
                                "name": file,
                                "path": video_path,
                                "thumbnail": get_thumbnail_path(
                                    video_path, self.thumbnail_dir
                                ),
                            }
                        )
        return jsonify(related_videos)
