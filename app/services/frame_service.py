from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Frame


def create_frame(db: Session, device_id: str, timestamp: int, file_path: str) -> Frame:
    frame = Frame(
        device_id=device_id,
        timestamp=timestamp,
        file_path=file_path,
    )
    db.add(frame)
    try:
        db.commit()
        db.refresh(frame)
        return frame
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Frame)
            .filter(Frame.device_id == device_id, Frame.timestamp == timestamp)
            .first()
        )
        if existing is not None:
            return existing
        raise


def get_frames(db: Session, limit: int = 50):
    return db.query(Frame).order_by(Frame.timestamp.desc()).limit(limit).all()


def get_recent_frames(db: Session, window_ms: int = 100):
    return db.query(Frame).order_by(Frame.timestamp.asc()).all()
