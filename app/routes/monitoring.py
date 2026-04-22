from fastapi import APIRouter, HTTPException

from app.services.monitoring_service import (
    get_camera_state,
    get_relay_status,
    list_camera_states,
)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get(
    "/cameras",
    summary="카메라별 stream 상태 목록 조회",
    description="Stream Server in-memory state에 기록된 카메라별 최신 프레임 상태를 반환합니다.",
)
def list_cameras():
    return {
        "items": list_camera_states(),
    }


@router.get(
    "/cameras/{device_id}",
    summary="단일 카메라 stream 상태 조회",
    description="Stream Server in-memory state에 기록된 단일 카메라의 최신 프레임 상태를 반환합니다.",
)
def get_camera(device_id: str):
    camera = get_camera_state(device_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera state not found")
    return camera


@router.get(
    "/relay",
    summary="Stream relay 상태 조회",
    description="Stream Server에서 Processing Server로 전달하는 gRPC relay worker 상태를 반환합니다.",
)
def get_relay():
    return get_relay_status()
