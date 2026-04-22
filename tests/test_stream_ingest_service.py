from pathlib import Path

from app.services.stream_ingest_service import ingest_frame
from app.services.stream_state import StreamState


def test_ingest_frame_saves_file_registers_metadata_and_updates_state(
    session_factory,
    storage_dir,
):
    db = session_factory()
    state = StreamState()
    try:
        result = ingest_frame(
            db,
            device_id="camera1",
            timestamp_ms=1712321562400,
            sequence=7,
            content_type="image/jpeg",
            image_bytes=b"frame-bytes",
            state=state,
        )

        frame = result["frame"]
        camera_state = result["camera_state"]

        assert frame.id is not None
        assert frame.device_id == "camera1"
        assert frame.timestamp == 1712321562400
        assert Path(frame.file_path).is_file()
        assert Path(frame.file_path).read_bytes() == b"frame-bytes"
        assert str(storage_dir) in frame.file_path

        assert camera_state.latest_frame is not None
        assert camera_state.latest_frame.frame_id == frame.id
        assert camera_state.latest_frame.sequence == 7
        assert camera_state.latest_frame.image_bytes_size == len(b"frame-bytes")
    finally:
        db.close()


def test_ingest_frame_uses_duplicate_registration_fallback(
    session_factory,
    storage_dir,
):
    db = session_factory()
    state = StreamState()
    try:
        first = ingest_frame(
            db,
            device_id="camera1",
            timestamp_ms=1000,
            sequence=1,
            image_bytes=b"first",
            state=state,
        )
        second = ingest_frame(
            db,
            device_id="camera1",
            timestamp_ms=1000,
            sequence=2,
            image_bytes=b"second",
            state=state,
        )

        assert second["frame"].id == first["frame"].id
        assert second["frame"].file_path == first["frame"].file_path
        assert Path(second["frame"].file_path).read_bytes() == b"second"
        assert str(storage_dir) in second["frame"].file_path
        assert second["camera_state"].latest_frame is not None
        assert second["camera_state"].latest_frame.sequence == 2
    finally:
        db.close()
