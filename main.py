from flask import Flask
from flask_caching import Cache
from services import VideoServer
import logging


def create_app(config_path="config.ini"):
    app = Flask(__name__)

    # Configure logging to suppress most logs
    logging.basicConfig(level=logging.CRITICAL)  # Only show critical logs

    # Initialize cache
    cache = Cache(app, config={"CACHE_TYPE": "null"})

    # Initialize VideoServer
    try:
        video_server = VideoServer(app, cache, config_path)
    except Exception as e:
        logging.error(f"Failed to initialize VideoServer: {e}")
        raise

    return app, video_server


if __name__ == "__main__":
    try:
        app, video_server = create_app()
        video_server.run()
    except Exception as e:
        logging.error(f"Application failed to start: {e}")
