import os
import re
from datetime import datetime
from pathlib import Path

from app.config.server import STORAGE_DIR


def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)


def build_frame_path(device_id: str, timestamp: int, filename: str) -> str:
    dt = datetime.fromtimestamp(timestamp / 1000)

    folder = os.path.join(
        STORAGE_DIR,
        device_id,
        str(dt.year),
        f"{dt.month:02d}",
        f"{dt.day:02d}",
    )
    ensure_dir(folder)

    safe_name = f"{timestamp}_{filename}"
    return os.path.join(folder, safe_name)


def parse_filename(filename: str):
    """
    camera1_1712321562400.jpg
    -> device_id: camera1
    -> timestamp: 1712321562400
    """
    pattern = r"^(camera\d+)_(\d+)\.jpg$"
    match = re.match(pattern, filename)

    if not match:
        raise ValueError("Filename format is invalid.")

    device_id = match.group(1)
    timestamp = int(match.group(2))

    return device_id, timestamp
