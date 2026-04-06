import httpx
from sqlalchemy.orm import Session, joinedload

from app.models import Frame, SyncGroup, SyncFrame

def create_sync_group(db: Session, group_timestamp: int, frame_ids: list[int]) -> SyncGroup:
    group = SyncGroup(group_timestamp=group_timestamp)
    db.add(group)
    db.flush()

    for frame_id in frame_ids:
        item = SyncFrame(sync_group_id=group.id, frame_id=frame_id)
        db.add(item)

    db.commit()
    db.refresh(group)
    return group


def get_sync_groups(db: Session, limit: int = 20):
    groups = (
        db.query(SyncGroup)
        .options(joinedload(SyncGroup.frames).joinedload(SyncFrame.frame))
        .order_by(SyncGroup.group_timestamp.desc())
        .limit(limit)
        .all()
    )

    result = []
    for group in groups:
        result.append({
            "id": group.id,
            "group_timestamp": group.group_timestamp,
            "frames": [
                {
                    "id": item.frame.id,
                    "device_id": item.frame.device_id,
                    "timestamp": item.frame.timestamp,
                    "file_path": item.frame.file_path,
                }
                for item in group.frames
            ]
        })

    return result

def get_sync_group_by_id(db: Session, group_id: int):
    group = (
        db.query(SyncGroup)
        .options(joinedload(SyncGroup.frames).joinedload(SyncFrame.frame))
        .filter(SyncGroup.id == group_id)
        .first()
    )

    if not group:
        return None

    return {
        "id": group.id,
        "group_timestamp": group.group_timestamp,
        "frames": [
            {
                "id": item.frame.id,
                "device_id": item.frame.device_id,
                "timestamp": item.frame.timestamp,
                "file_path": item.frame.file_path,
            }
            for item in group.frames
        ]
    }


def get_unsynced_frames(db: Session):
    return (
        db.query(Frame)
        .outerjoin(SyncFrame, SyncFrame.frame_id == Frame.id)
        .filter(SyncFrame.frame_id.is_(None))
        .order_by(Frame.timestamp.asc())
        .all()
    )


def build_sync_groups(db: Session, threshold_ms: int = 50):
    all_frames = get_unsynced_frames(db)

    used_frame_ids = set()
    created_groups = []
    window_start = 0
    window_end = 0

    for base_frame in all_frames:
        if base_frame.id in used_frame_ids:
            continue

        lower_bound = base_frame.timestamp - threshold_ms
        upper_bound = base_frame.timestamp + threshold_ms

        while window_start < len(all_frames) and all_frames[window_start].timestamp < lower_bound:
            window_start += 1

        if window_end < window_start:
            window_end = window_start

        while window_end < len(all_frames) and all_frames[window_end].timestamp <= upper_bound:
            window_end += 1

        selected = [base_frame]
        used_devices = {base_frame.device_id}

        for candidate in all_frames[window_start:window_end]:
            if candidate.id in used_frame_ids:
                continue
            if candidate.id == base_frame.id:
                continue
            if candidate.device_id in used_devices:
                continue

            if abs(candidate.timestamp - base_frame.timestamp) <= threshold_ms:
                selected.append(candidate)
                used_devices.add(candidate.device_id)

        if len(selected) >= 2:
            group = SyncGroup(group_timestamp=base_frame.timestamp)
            db.add(group)
            db.flush()

            for frame in selected:
                db.add(SyncFrame(sync_group_id=group.id, frame_id=frame.id))
                used_frame_ids.add(frame.id)

            created_groups.append(group)

    if created_groups:
        db.commit()
        for group in created_groups:
            db.refresh(group)

    return created_groups

def build_dispatch_payload(group: dict):
    return {
        "syncGroupId": group["id"],
        "groupTimestamp": group["group_timestamp"],
        "frames": [
            {
                "frameId": frame["id"],
                "deviceId": frame["device_id"],
                "timestamp": frame["timestamp"],
                "filePath": frame["file_path"],
            }
            for frame in group["frames"]
        ]
    }


def parse_response_body(response: httpx.Response):
    if not response.content:
        return None

    try:
        return response.json()
    except ValueError:
        return response.text


async def dispatch_sync_group(group: dict, processing_server_url: str):
    payload = build_dispatch_payload(group)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(processing_server_url, json=payload)
            response_body = parse_response_body(response)
            response.raise_for_status()

        return {
            "success": True,
            "status_code": response.status_code,
            "response_body": response_body,
            "payload": payload
        }

    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"Processing server returned HTTP {exc.response.status_code}",
            "status_code": exc.response.status_code,
            "response_body": parse_response_body(exc.response),
            "payload": payload,
        }

    except httpx.ConnectError:
        return {
            "success": False,
            "error": "Processing server connection failed",
            "payload": payload
        }

    except httpx.ReadTimeout:
        return {
            "success": False,
            "error": "Processing server timeout",
            "payload": payload
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "payload": payload
        }
