from flask import Flask
from flask_caching import Cache
from services import VideoServer

"""
Function to create and configure a Flask application instance.
Args:
    config_path (str): The path to the configuration file for the app and video server. Defaults to 'config.ini'.
Returns:
    app: A configured Flask application instance.
    video_server: An instance of the VideoServer, initialized with the app and cache.
"""
def create_app(config_path='config.ini'):
    # Create a Flask application instance
    app = Flask(__name__)

    # Initialize cache for the application (set to 'null' cache type for now)
    cache = Cache(app, config={'CACHE_TYPE': 'null'})

    # Initialize VideoServer with the Flask app, cache, and config path
    video_server = VideoServer(app, cache, config_path)

    return app, video_server

"""
Main entry point of the application.
Creates the Flask app and VideoServer, and starts the video server when run as the main script.
"""
if __name__ == '__main__':
    # Create the app and video server instances
    app, video_server = create_app()

    # Run the video server (likely starts the Flask app with additional functionality)
    video_server.run()
