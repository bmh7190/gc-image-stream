from pathlib import Path

from app.routes import sync as sync_routes


def test_register_frame_is_idempotent(client):
    first = client.post(
        "/frames/register",
        data={
            "device_id": "camera1",
            "timestamp": 1000,
            "file_path": "storage/camera1/1000.jpg",
        },
    )
    second = client.post(
        "/frames/register",
        data={
            "device_id": "camera1",
            "timestamp": 1000,
            "file_path": "storage/camera1/other.jpg",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["file_path"] == "storage/camera1/1000.jpg"


def test_upload_frame_saves_file_and_metadata(client, read_file_bytes):
    response = client.post(
        "/frames/upload",
        files={
            "file": (
                "camera1_1712321562400.jpg",
                b"frame-bytes",
                "image/jpeg",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["device_id"] == "camera1"
    assert body["timestamp"] == 1712321562400
    assert Path(body["file_path"]).is_file()
    assert read_file_bytes(body["file_path"]) == b"frame-bytes"


def test_sync_build_and_group_listing_flow(client):
    frame_inputs = [
        ("camera1", 1000, "storage/camera1/1000.jpg"),
        ("camera2", 1030, "storage/camera2/1030.jpg"),
        ("camera3", 1200, "storage/camera3/1200.jpg"),
    ]

    for device_id, timestamp, file_path in frame_inputs:
        response = client.post(
            "/frames/register",
            data={
                "device_id": device_id,
                "timestamp": timestamp,
                "file_path": file_path,
            },
        )
        assert response.status_code == 200

    build_response = client.post("/sync/build", params={"threshold_ms": 50})
    groups_response = client.get("/sync/groups")

    assert build_response.status_code == 200
    assert build_response.json() == {"created_count": 1}
    assert groups_response.status_code == 200

    groups = groups_response.json()
    assert len(groups) == 1
    assert groups[0]["group_timestamp"] == 1000
    assert groups[0]["dispatch_status"] == "pending"
    assert groups[0]["last_dispatch_at"] is None
    assert groups[0]["last_dispatch_status_code"] is None
    assert groups[0]["last_dispatch_error"] is None
    assert groups[0]["dispatched_at"] is None
    assert {frame["device_id"] for frame in groups[0]["frames"]} == {"camera1", "camera2"}


def test_dispatch_endpoint_returns_dispatch_service_result(client, monkeypatch):
    for device_id, timestamp in [("camera1", 1000), ("camera2", 1010)]:
        response = client.post(
            "/frames/register",
            data={
                "device_id": device_id,
                "timestamp": timestamp,
                "file_path": f"storage/{device_id}/{timestamp}.jpg",
            },
        )
        assert response.status_code == 200

    build_response = client.post("/sync/build", params={"threshold_ms": 20})
    assert build_response.status_code == 200

    captured = {}

    async def fake_dispatch(group, processing_server_url):
        captured["group"] = group
        captured["processing_server_url"] = processing_server_url
        return {
            "success": True,
            "status_code": 200,
            "response_body": {"message": "ok"},
            "payload": {"syncGroupId": group["id"]},
        }

    monkeypatch.setattr(sync_routes, "dispatch_sync_group", fake_dispatch)

    groups_response = client.get("/sync/groups")
    group_id = groups_response.json()[0]["id"]

    dispatch_response = client.post(f"/sync/groups/{group_id}/dispatch")
    group_response = client.get(f"/sync/groups/{group_id}")

    assert dispatch_response.status_code == 200
    assert dispatch_response.json()["success"] is True
    assert dispatch_response.json()["payload"] == {"syncGroupId": group_id}
    assert group_response.status_code == 200
    assert group_response.json()["dispatch_status"] == "success"
    assert group_response.json()["last_dispatch_status_code"] == 200
    assert group_response.json()["last_dispatch_error"] is None
    assert group_response.json()["last_dispatch_at"] is not None
    assert group_response.json()["dispatched_at"] is not None
    assert captured["group"]["id"] == group_id
    assert captured["processing_server_url"] == sync_routes.PROCESSING_SERVER_URL


def test_dispatch_endpoint_tracks_failed_dispatch_state(client, monkeypatch):
    for device_id, timestamp in [("camera1", 1000), ("camera2", 1010)]:
        response = client.post(
            "/frames/register",
            data={
                "device_id": device_id,
                "timestamp": timestamp,
                "file_path": f"storage/{device_id}/{timestamp}.jpg",
            },
        )
        assert response.status_code == 200

    build_response = client.post("/sync/build", params={"threshold_ms": 20})
    assert build_response.status_code == 200

    async def fake_dispatch(group, processing_server_url):
        return {
            "success": False,
            "error": "Processing server timeout",
            "payload": {"syncGroupId": group["id"]},
        }

    monkeypatch.setattr(sync_routes, "dispatch_sync_group", fake_dispatch)

    groups_response = client.get("/sync/groups")
    group_id = groups_response.json()[0]["id"]

    dispatch_response = client.post(f"/sync/groups/{group_id}/dispatch")
    group_response = client.get(f"/sync/groups/{group_id}")

    assert dispatch_response.status_code == 200
    assert dispatch_response.json()["success"] is False
    assert group_response.status_code == 200
    assert group_response.json()["dispatch_status"] == "failed"
    assert group_response.json()["last_dispatch_status_code"] is None
    assert group_response.json()["last_dispatch_error"] == "Processing server timeout"
    assert group_response.json()["last_dispatch_at"] is not None
    assert group_response.json()["dispatched_at"] is None
