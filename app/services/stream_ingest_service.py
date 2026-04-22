from pathlib import Path

from sqlalchemy.orm import Session

from app.services.frame_service import create_frame
from app.services.stream_state import StreamState, stream_state
from app.utils.file_utils import build_frame_path


def ingest_frame(
    db: Session,
    device_id: str,
    timestamp_ms: int,
    image_bytes: bytes,
    sequence: int | None = None,
    content_type: str = "image/jpeg",
    filename: str | None = None,
    state: StreamState = stream_state,
):
    target_filename = filename or f"{device_id}_{timestamp_ms}.jpg"
    save_path = build_frame_path(device_id, timestamp_ms, target_filename)
    Path(save_path).write_bytes(image_bytes)

    frame = create_frame(
        db,
        device_id=device_id,
        timestamp=timestamp_ms,
        file_path=save_path,
    )

    camera_state = state.update_frame(
        frame_id=frame.id,
        device_id=frame.device_id,
        timestamp=frame.timestamp,
        sequence=sequence,
        file_path=frame.file_path,
        content_type=content_type,
        image_bytes_size=len(image_bytes),
    )

    return {
        "frame": frame,
        "camera_state": camera_state,
    }
