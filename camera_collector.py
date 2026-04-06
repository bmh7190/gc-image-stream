import os
import sys
import time
from datetime import datetime
import urllib.request
import requests
from dotenv import load_dotenv


def load_env_file():
    env_file = ".env"
    if len(sys.argv) > 1:
        env_file = sys.argv[1]

    load_dotenv(env_file)
    print(f"[ENV] loaded: {env_file}")


load_env_file()

CAMERA_NAME = os.getenv("CAMERA_NAME")
CAMERA_URL = os.getenv("CAMERA_SNAPSHOT_URL")
INTERVAL_SEC = float(os.getenv("COLLECT_INTERVAL_SEC", "1.0"))
BASE_DIR = os.getenv("STORAGE_DIR", "storage")
REGISTER_API_URL = os.getenv("REGISTER_API_URL", "http://127.0.0.1:8000/frames/register")


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def build_save_path(camera_name: str, timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000)

    folder = os.path.join(
        BASE_DIR,
        camera_name,
        str(dt.year),
        f"{dt.month:02d}",
        f"{dt.day:02d}"
    )
    ensure_dir(folder)

    filename = f"{camera_name}_{timestamp_ms}.jpg"
    return os.path.join(folder, filename)


def download_image(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read()


def register_to_server(device_id: str, timestamp: int, file_path: str):
    try:
        data = {
            "device_id": device_id,
            "timestamp": str(timestamp),
            "file_path": file_path
        }

        response = requests.post(REGISTER_API_URL, data=data, timeout=5)

        if response.status_code == 200:
            print(f"[DB REGISTERED] {response.json()}")
        else:
            print(f"[REGISTER FAILED] status={response.status_code}, body={response.text}")

    except Exception as e:
        print(f"[REGISTER ERROR] {e}")


def validate_config():
    missing = []
    if not CAMERA_NAME:
        missing.append("CAMERA_NAME")
    if not CAMERA_URL:
        missing.append("CAMERA_SNAPSHOT_URL")

    if missing:
        raise ValueError(f"Missing env values: {', '.join(missing)}")


def main():
    validate_config()

    print(f"[START] collecting from {CAMERA_NAME}")
    print(f"[URL] {CAMERA_URL}")
    print(f"[INTERVAL] {INTERVAL_SEC}s")
    print(f"[REGISTER API] {REGISTER_API_URL}")
    print(f"[STORAGE DIR] {BASE_DIR}")

    while True:
        try:
            start_time = time.time()

            image_bytes = download_image(CAMERA_URL)
            timestamp_ms = int(time.time() * 1000)

            save_path = build_save_path(CAMERA_NAME, timestamp_ms)

            with open(save_path, "wb") as f:
                f.write(image_bytes)

            elapsed = time.time() - start_time
            print(f"[SAVED] {save_path} ({elapsed:.3f}s)")

            register_to_server(CAMERA_NAME, timestamp_ms, save_path)

        except Exception as e:
            print(f"[ERROR] image request failed: {e}")

        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()