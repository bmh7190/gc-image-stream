import asyncio

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import SyncFrame, SyncGroup
from app.services.frame_service import create_frame
from app.services.sync_service import (
    build_dispatch_payload,
    build_sync_groups,
    create_sync_group,
    dispatch_sync_group,
    record_sync_group_dispatch_result,
)


def build_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_factory()


def test_build_dispatch_payload_maps_response_shape():
    group = {
        "id": 12,
        "group_timestamp": 1712321562400,
        "frames": [
            {
                "id": 1,
                "device_id": "camera1",
                "timestamp": 1712321562400,
                "file_path": "storage/camera1/1.jpg",
            },
            {
                "id": 2,
                "device_id": "camera2",
                "timestamp": 1712321562430,
                "file_path": "storage/camera2/2.jpg",
            },
        ],
    }

    payload = build_dispatch_payload(group)

    assert payload == {
        "syncGroupId": 12,
        "groupTimestamp": 1712321562400,
        "frames": [
            {
                "frameId": 1,
                "deviceId": "camera1",
                "timestamp": 1712321562400,
                "filePath": "storage/camera1/1.jpg",
            },
            {
                "frameId": 2,
                "deviceId": "camera2",
                "timestamp": 1712321562430,
                "filePath": "storage/camera2/2.jpg",
            },
        ],
    }


def test_dispatch_sync_group_returns_failure_for_http_error(monkeypatch):
    group = {
        "id": 12,
        "group_timestamp": 1712321562400,
        "frames": [],
    }

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            request = httpx.Request("POST", url, json=json)
            return httpx.Response(
                500,
                request=request,
                json={"detail": "processing failed"},
            )

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=5.0: FakeAsyncClient())

    result = asyncio.run(dispatch_sync_group(group, "http://processing.local/process"))

    assert result == {
        "success": False,
        "error": "Processing server returned HTTP 500",
        "status_code": 500,
        "response_body": {"detail": "processing failed"},
        "payload": {
            "syncGroupId": 12,
            "groupTimestamp": 1712321562400,
            "frames": [],
        },
    }


def test_dispatch_sync_group_accepts_non_json_success_body(monkeypatch):
    group = {
        "id": 13,
        "group_timestamp": 1712321562500,
        "frames": [],
    }

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            request = httpx.Request("POST", url, json=json)
            return httpx.Response(
                200,
                request=request,
                text="accepted",
            )

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=5.0: FakeAsyncClient())

    result = asyncio.run(dispatch_sync_group(group, "http://processing.local/process"))

    assert result == {
        "success": True,
        "status_code": 200,
        "response_body": "accepted",
        "payload": {
            "syncGroupId": 13,
            "groupTimestamp": 1712321562500,
            "frames": [],
        },
    }


def test_build_sync_groups_creates_group_only_from_unsynced_frames_within_threshold():
    db = build_test_session()
    try:
        first = create_frame(db, "camera1", 1000, "storage/camera1/1000.jpg")
        second = create_frame(db, "camera2", 1030, "storage/camera2/1030.jpg")
        create_frame(db, "camera3", 1200, "storage/camera3/1200.jpg")

        groups = build_sync_groups(db, threshold_ms=50)

        assert len(groups) == 1
        synced_frame_ids = {item.frame_id for item in db.query(SyncFrame).all()}
        assert synced_frame_ids == {first.id, second.id}
    finally:
        db.close()


def test_build_sync_groups_skips_frames_already_assigned_to_existing_group():
    db = build_test_session()
    try:
        existing = create_frame(db, "camera1", 1000, "storage/camera1/1000.jpg")
        create_sync_group(db, 1000, [existing.id])
        second = create_frame(db, "camera2", 1010, "storage/camera2/1010.jpg")
        third = create_frame(db, "camera3", 1020, "storage/camera3/1020.jpg")

        groups = build_sync_groups(db, threshold_ms=30)

        assert len(groups) == 1
        synced_frame_ids = {item.frame_id for item in db.query(SyncFrame).all()}
        assert synced_frame_ids == {existing.id, second.id, third.id}
    finally:
        db.close()


def test_build_sync_groups_keeps_only_one_frame_per_device_in_group():
    db = build_test_session()
    try:
        first = create_frame(db, "camera1", 1000, "storage/camera1/1000.jpg")
        create_frame(db, "camera1", 1005, "storage/camera1/1005.jpg")
        third = create_frame(db, "camera2", 1010, "storage/camera2/1010.jpg")

        groups = build_sync_groups(db, threshold_ms=20)

        assert len(groups) == 1
        synced_frame_ids = {item.frame_id for item in db.query(SyncFrame).all()}
        assert synced_frame_ids == {first.id, third.id}
    finally:
        db.close()


def test_record_sync_group_dispatch_result_marks_success_and_failure():
    db = build_test_session()
    try:
        group = SyncGroup(group_timestamp=1000, dispatch_status="pending")
        db.add(group)
        db.commit()
        db.refresh(group)

        success_group = record_sync_group_dispatch_result(
            db,
            group.id,
            {
                "success": True,
                "status_code": 200,
                "response_body": {"message": "ok"},
            },
        )

        assert success_group.dispatch_status == "success"
        assert success_group.last_dispatch_status_code == 200
        assert success_group.last_dispatch_error is None
        assert success_group.last_dispatch_at is not None
        assert success_group.dispatched_at is not None

        failed_group = record_sync_group_dispatch_result(
            db,
            group.id,
            {
                "success": False,
                "error": "Processing server timeout",
            },
        )

        assert failed_group.dispatch_status == "failed"
        assert failed_group.last_dispatch_status_code is None
        assert failed_group.last_dispatch_error == "Processing server timeout"
        assert failed_group.last_dispatch_at is not None
        assert failed_group.dispatched_at is not None
    finally:
        db.close()
