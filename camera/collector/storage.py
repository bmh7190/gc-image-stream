import os
from datetime import datetime


LEGACY_COLLECTOR_STORAGE_NOTE = (
    "Standalone collector local storage is a transitional fallback. "
    "Primary Stream Server storage happens through ingest_frame()."
)


def ensure_legacy_collector_dir(path: str):
    os.makedirs(path, exist_ok=True)


def build_legacy_collector_save_path(
    camera_name: str,
    timestamp_ms: int,
    base_dir: str,
) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000)

    folder = os.path.join(
        base_dir,
        camera_name,
        str(dt.year),
        f"{dt.month:02d}",
        f"{dt.day:02d}",
    )
    ensure_legacy_collector_dir(folder)

    filename = f"{camera_name}_{timestamp_ms}.jpg"
    return os.path.join(folder, filename)


def save_legacy_collector_image(save_path: str, image_bytes: bytes):
    with open(save_path, "wb") as file_obj:
        file_obj.write(image_bytes)


# Backward-compatible aliases for older standalone collector imports.
ensure_dir = ensure_legacy_collector_dir
build_save_path = build_legacy_collector_save_path
save_image = save_legacy_collector_image
