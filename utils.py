import os
import socket
import hashlib
import subprocess
from typing import List, Optional
import logging

# Suppress logging in utils.py
logging.basicConfig(level=logging.CRITICAL)


def get_ip_addresses() -> List[str]:
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname_ex(hostname)[2]
    except Exception as e:
        logging.error(f"Error getting IP addresses: {e}")
        return []


def directory_contains_supported_files(
    path: str, extensions: List[str], show_hidden: bool
) -> bool:
    try:
        for root, dirs, files in os.walk(path):
            if not show_hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files = [f for f in files if not f.startswith(".")]
            if any(f.lower().endswith(tuple(extensions)) for f in files):
                return True
        return False
    except Exception as e:
        logging.error(f"Error checking directory for supported files: {e}")
        return False


def get_thumbnail_path(video_path: str, thumbnail_dir: str) -> str:
    try:
        unique_id = hashlib.md5(video_path.encode("utf-8")).hexdigest()
        thumbnail_filename = (
            f"{os.path.splitext(os.path.basename(video_path))[0]}_{unique_id}.jpg"
        )
        return os.path.join(thumbnail_dir, thumbnail_filename)
    except Exception as e:
        logging.error(f"Error generating thumbnail path: {e}")
        return ""


def extract_subtitles(video_path: str) -> Optional[str]:
    output_path = os.path.splitext(video_path)[0] + ".vtt"
    if not os.path.exists(output_path):
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-hwaccel",
                    "auto",
                    "-i",
                    video_path,
                    "-map",
                    "0:s:0",
                    output_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as e:
            logging.error(f"Error extracting subtitles: {e}")
            return None
    return output_path


def generate_thumbnail(video_path: str, thumbnail_path: str) -> Optional[str]:
    if not os.path.exists(thumbnail_path):
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-hwaccel",
                    "auto",
                    "-i",
                    video_path,
                    "-ss",
                    "00:00:05",
                    "-vframes",
                    "1",
                    "-vf",
                    "scale=320:-1",
                    thumbnail_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as e:
            logging.error(f"Error generating thumbnail: {e}")
            return None
    return thumbnail_path
