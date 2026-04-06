from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config.server import PROCESSING_SERVER_URL
from app.db import get_db
from app.schemas import SyncGroupResponse, SyncSummaryResponse
from app.services.sync_service import (
    build_sync_groups,
    can_manually_retry_group,
    dispatch_sync_group,
    get_sync_group_by_id,
    get_sync_groups,
    get_sync_summary,
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
    status: str | None = Query(default=None),
    retry_ready: bool | None = Query(default=None),
    exhausted: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return get_sync_groups(
        db,
        limit=limit,
        dispatch_status=status,
        retry_ready=retry_ready,
        exhausted=exhausted,
    )


@router.get("/summary", response_model=SyncSummaryResponse)
def get_summary(
    db: Session = Depends(get_db),
):
    return get_sync_summary(db)


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
    record_sync_group_dispatch_result(db, group_id, result, source="manual_dispatch")
    return result


@router.post("/groups/{group_id}/retry")
async def retry_group(
    group_id: int,
    db: Session = Depends(get_db),
):
    group = get_sync_group_by_id(db, group_id)

    if group is None:
        raise HTTPException(status_code=404, detail="Sync group not found")

    if not can_manually_retry_group(group):
        raise HTTPException(
            status_code=400,
            detail="Successful sync groups cannot be retried manually",
        )

    result = await dispatch_sync_group(group, PROCESSING_SERVER_URL)
    record_sync_group_dispatch_result(db, group_id, result, source="manual_retry")
    return result
