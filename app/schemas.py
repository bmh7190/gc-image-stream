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
    frames: list[SyncFrameDetail]
