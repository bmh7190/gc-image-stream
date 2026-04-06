from pydantic import BaseModel, ConfigDict


class FrameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    timestamp: int
    file_path: str


class SyncFrameDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    timestamp: int
    file_path: str


class SyncGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_timestamp: int
    dispatch_status: str
    last_dispatch_at: int | None = None
    last_dispatch_status_code: int | None = None
    last_dispatch_error: str | None = None
    dispatched_at: int | None = None
    retry_count: int
    next_retry_at: int | None = None
    frames: list[SyncFrameDetail]


class SyncGroupListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SyncGroupResponse]


class SyncSummaryResponse(BaseModel):
    total_groups: int
    pending: int
    retry_scheduled: int
    success: int
    failed: int
    exhausted: int
    retry_ready: int
