from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.debug_service import get_latest_timestamp_delta
from app.services.monitoring_service import get_latest_frame_path

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get(
    "/cameras/{device_id}/latest-frame",
    summary="카메라 최신 프레임 이미지 조회",
    description="StreamState 또는 DB 기준 최신 프레임 파일을 이미지 응답으로 반환합니다.",
)
def get_latest_frame(device_id: str, db: Session = Depends(get_db)):
    file_path = get_latest_frame_path(db, device_id)
    if file_path is None:
        raise HTTPException(status_code=404, detail="Latest frame not found")
    return FileResponse(file_path)


@router.get(
    "/timestamp-delta",
    summary="카메라 최신 timestamp 차이 조회",
    description="StreamState 기준 각 카메라의 최신 timestamp와 기준 timestamp 사이의 차이를 반환합니다.",
)
def get_timestamp_delta():
    return get_latest_timestamp_delta()
