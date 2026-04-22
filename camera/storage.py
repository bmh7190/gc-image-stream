import os
from datetime import datetime


# 저장 경로가 없으면 생성한다.
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


# 카메라명과 timestamp 기준으로 저장 경로를 만든다.
def build_save_path(camera_name: str, timestamp_ms: int, base_dir: str) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000)

    folder = os.path.join(
        base_dir,
        camera_name,
        str(dt.year),
        f"{dt.month:02d}",
        f"{dt.day:02d}",
    )
    ensure_dir(folder)

    filename = f"{camera_name}_{timestamp_ms}.jpg"
    return os.path.join(folder, filename)


# 이미지 바이트를 파일로 저장한다.
def save_image(save_path: str, image_bytes: bytes):
    with open(save_path, "wb") as file_obj:
        file_obj.write(image_bytes)
