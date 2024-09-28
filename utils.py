import os
import socket
import hashlib
import subprocess
from typing import List, Optional

"""
Function to retrieve the list of IP addresses of the current machine.
Returns a list of strings containing IP addresses.
If an error occurs, an empty list is returned.
"""
def get_ip_addresses() -> List[str]:
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname_ex(hostname)[2]
    except Exception as e:
        print(f"Error getting IP addresses: {e}")
        return []

"""
Function to check if a directory contains any supported files with specified extensions.
Args:
    path (str): The directory path to check.
    extensions (List[str]): A list of file extensions to consider as supported.
    show_hidden (bool): A flag indicating whether hidden files should be considered.
Returns True if any supported files are found, otherwise False.
"""
def directory_contains_supported_files(path: str, extensions: List[str], show_hidden: bool) -> bool:
    for root, dirs, files in os.walk(path):
        if not show_hidden:
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            files = [f for f in files if not f.startswith('.')]
        if any(f.lower().endswith(tuple(extensions)) for f in files):
            return True
    return False

"""
Function to generate a unique thumbnail path for a video file.
Args:
    video_path (str): The path to the video file.
    thumbnail_dir (str): The directory where thumbnails are stored.
Returns the full path to the thumbnail file, based on the video file's name and a unique hash.
"""
def get_thumbnail_path(video_path: str, thumbnail_dir: str) -> str:
    unique_id = hashlib.md5(video_path.encode('utf-8')).hexdigest()
    thumbnail_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}_{unique_id}.jpg"
    return os.path.join(thumbnail_dir, thumbnail_filename)

"""
Function to extract subtitles from a video file and save them in VTT format.
Args:
    video_path (str): The path to the video file.
Returns the path to the subtitle file if extraction is successful, or None if it fails.
"""
def extract_subtitles(video_path: str) -> Optional[str]:
    output_path = os.path.splitext(video_path)[0] + '.vtt'
    if not os.path.exists(output_path):
        try:
            subprocess.run(
                ['ffmpeg', '-hwaccel', 'auto', '-i', video_path, '-map', '0:s:0', output_path],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            return None
    return output_path

"""
Function to generate a thumbnail for a video at a specific timestamp (5 seconds).
Args:
    video_path (str): The path to the video file.
    thumbnail_path (str): The path where the generated thumbnail will be saved.
Returns the path to the generated thumbnail, or None if thumbnail generation fails.
"""
def generate_thumbnail(video_path: str, thumbnail_path: str) -> Optional[str]:
    if not os.path.exists(thumbnail_path):
        try:
            subprocess.run([
                'ffmpeg', '-hwaccel', 'auto', '-i', video_path,
                '-ss', '00:00:05', '-vframes', '1', '-vf', 'scale=320:-1',
                thumbnail_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            return None
    return thumbnail_path
