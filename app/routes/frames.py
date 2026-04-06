from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
import os
import shutil

from app.db import get_db
from app.schemas import FrameResponse
from app.services.frame_service import create_frame, get_frames
from app.utils.file_utils import build_frame_path, parse_filename

router = APIRouter(prefix="/frames", tags=["frames"])


def remove_file_if_exists(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


@router.post("/upload")
async def upload_frame(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    try:
        device_id, timestamp = parse_filename(file.filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Filename format is invalid.")

    save_path = build_frame_path(device_id, timestamp, file.filename)

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        frame = create_frame(
            db=db,
            device_id=device_id,
            timestamp=timestamp,
            file_path=save_path
        )
    except Exception as exc:
        db.rollback()
        remove_file_if_exists(save_path)
        raise HTTPException(
            status_code=500,
            detail="Failed to persist uploaded frame.",
        ) from exc

    return frame

@router.post("/register", response_model=FrameResponse)
def register_frame(
    device_id: str = Form(...),
    timestamp: int = Form(...),
    file_path: str = Form(...),
    db: Session = Depends(get_db)
):
    frame = create_frame(
        db=db,
        device_id=device_id,
        timestamp=timestamp,
        file_path=file_path
    )
    return frame

@router.get("", response_model=list[FrameResponse])
def list_frames(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    return get_frames(db, limit)
