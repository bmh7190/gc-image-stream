from pydantic import BaseModel, ConfigDict, Field


class FrameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="수집 DB에 저장된 프레임 레코드 ID입니다.")
    device_id: str = Field(description="프레임을 생성한 카메라 또는 디바이스 식별자입니다.")
    timestamp: int = Field(description="프레임 촬영 시각입니다. 밀리초 단위입니다.")
    file_path: str = Field(description="수집된 프레임 이미지가 저장된 파일 경로입니다.")


class SyncFrameDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="수집 DB에 저장된 프레임 레코드 ID입니다.")
    device_id: str = Field(description="이 프레임의 카메라 또는 디바이스 식별자입니다.")
    timestamp: int = Field(description="프레임 촬영 시각입니다. 밀리초 단위입니다.")
    file_path: str = Field(description="수집된 프레임 이미지가 저장된 파일 경로입니다.")


class SyncGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="sync group ID입니다.")
    group_timestamp: int = Field(
        description="sync group을 대표하는 기준 timestamp입니다. 밀리초 단위입니다."
    )
    dispatch_status: str = Field(
        description=(
            "현재 dispatch 상태입니다. "
            "pending, retry_scheduled, success, failed, exhausted 중 하나입니다."
        )
    )
    last_dispatch_at: int | None = Field(
        default=None,
        description="마지막 dispatch 시도 시각입니다. 값이 있으면 밀리초 단위입니다.",
    )
    last_dispatch_status_code: int | None = Field(
        default=None,
        description="마지막 dispatch에서 처리 서버가 반환한 HTTP 상태 코드입니다.",
    )
    last_dispatch_error: str | None = Field(
        default=None,
        description="이 그룹에 대해 마지막으로 기록된 dispatch 에러 메시지입니다.",
    )
    dispatched_at: int | None = Field(
        default=None,
        description="성공적으로 dispatch된 시각입니다. 값이 있으면 밀리초 단위입니다.",
    )
    retry_count: int = Field(
        description="이 sync group에 대해 시도한 재시도 횟수입니다."
    )
    next_retry_at: int | None = Field(
        default=None,
        description="재시도 가능한 실패에 대해 다음 재시도 예정 시각입니다. 밀리초 단위입니다.",
    )
    frames: list[SyncFrameDetail] = Field(
        description="이 sync group에 포함된 프레임 목록입니다."
    )


class SyncGroupListResponse(BaseModel):
    total: int = Field(description="현재 필터 조건에 맞는 전체 sync group 개수입니다.")
    limit: int = Field(description="이번 응답에 적용된 페이지 크기입니다.")
    offset: int = Field(description="이번 응답에 적용된 시작 offset입니다.")
    items: list[SyncGroupResponse] = Field(
        description="필터, 정렬, 페이지네이션이 적용된 현재 페이지의 sync group 목록입니다."
    )


class SyncSummaryResponse(BaseModel):
    total_groups: int = Field(description="DB에 저장된 전체 sync group 개수입니다.")
    pending: int = Field(description="아직 dispatch되지 않은 그룹 개수입니다.")
    retry_scheduled: int = Field(
        description="재시도 예정 상태로 대기 중인 그룹 개수입니다."
    )
    success: int = Field(description="성공적으로 dispatch된 그룹 개수입니다.")
    failed: int = Field(
        description="재시도 대상이 아닌 실패 그룹 개수입니다."
    )
    exhausted: int = Field(
        description="재시도 한도에 도달한 그룹 개수입니다."
    )
    retry_ready: int = Field(
        description="재시도 예정 시각이 이미 도래한 retry_scheduled 그룹 개수입니다."
    )
