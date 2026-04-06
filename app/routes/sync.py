from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config.server import PROCESSING_SERVER_URL
from app.db import get_db
from app.schemas import SyncGroupResponse
from app.services.sync_service import (
    build_sync_groups,
    dispatch_sync_group,
    get_sync_group_by_id,
    get_sync_groups,
    record_sync_group_dispatch_result,
)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/build")
def build_groups(
    threshold_ms: int = 50,
    db: Session = Depends(get_db),
):
    groups = build_sync_groups(db, threshold_ms=threshold_ms)
    return {
        "created_count": len(groups),
    }


@router.get("/groups", response_model=list[SyncGroupResponse])
def list_groups(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    return get_sync_groups(db, limit)


@router.get("/groups/{group_id}", response_model=SyncGroupResponse)
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
):
    group = get_sync_group_by_id(db, group_id)

    if group is None:
        raise HTTPException(status_code=404, detail="Sync group not found")

    return group


@router.post("/groups/{group_id}/dispatch")
async def dispatch_group(
    group_id: int,
    db: Session = Depends(get_db),
):
    group = get_sync_group_by_id(db, group_id)

    if group is None:
        raise HTTPException(status_code=404, detail="Sync group not found")

    result = await dispatch_sync_group(group, PROCESSING_SERVER_URL)
    record_sync_group_dispatch_result(db, group_id, result)
    return result
