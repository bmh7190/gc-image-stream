# GC Image Stream

`GC Image Stream` is a collection backend for multi-camera image pipelines.

This repository is responsible for:

- collecting frame data from camera apps or camera streams
- storing image files and frame metadata
- building timestamp-based sync groups
- dispatching grouped payloads to an external processing server

This repository does **not** implement the processing server itself. Its job is to supply clean, stable input to that external system.

## Scope

The current scope of this repository is limited to the collection pipeline:

1. ingest frames from multiple cameras
2. save files and metadata safely
3. group nearby timestamps across devices
4. send grouped data to an external processing server

Out of scope:

- processing server internals
- 3D reconstruction
- pose estimation
- skeleton analysis
- risk analysis or guidance generation

## Current Features

- FastAPI-based frame upload and registration endpoints
- local file storage for collected frames
- SQLite-based metadata management
- timestamp-based sync grouping
- manual and automatic dispatch
- dispatch state tracking per sync group
- retry scheduling for retryable dispatch failures
- operational retry controls for failed sync groups
- automated tests for core collection/grouping/dispatch logic

## Repository Structure

```text
app/
  config/           configuration loading and separation
  routes/           API routes
  services/         frame/group/dispatch business logic
  utils/            file/path utilities
camera_collector.py collector script for camera snapshots
fake_camera_generator.py test data generator for fake cameras
tests/              automated tests
docs/               project documents
```

## Quick Start

### 1. Create a virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Configure environment variables

Create a root `.env` file for server settings.

Example:

```env
DATABASE_URL=sqlite:///./frames.db
STORAGE_DIR=storage
PROCESSING_SERVER_URL=http://127.0.0.1:9000/process
```

If you use collector scripts, prepare per-camera env files such as `.env.camera1`.

Example:

```env
CAMERA_NAME=camera1
CAMERA_SNAPSHOT_URL=http://127.0.0.1:8080/shot.jpg
CAMERA_STREAM_URL=http://127.0.0.1:8080/video
COLLECT_INTERVAL_SEC=1.0
REGISTER_API_URL=http://127.0.0.1:8000/frames/register
```

### 3. Run the server

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

### 4. Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## API Summary

### Frames

- `POST /frames/upload`
- `POST /frames/register`
- `GET /frames`

### Sync

- `POST /sync/build`
- `GET /sync/summary`
- `GET /sync/groups`
- `GET /sync/groups/{group_id}`
- `POST /sync/groups/{group_id}/dispatch`
- `POST /sync/groups/{group_id}/retry`

`GET /sync/summary` returns an operational summary across sync groups:

- `total_groups`
- `pending`
- `retry_scheduled`
- `success`
- `failed`
- `exhausted`
- `retry_ready`

`GET /sync/groups` supports operational filters:

- `status=pending|retry_scheduled|success|failed|exhausted`
- `retry_ready=true|false`
- `exhausted=true|false`
- `limit=1..100`
- `offset=0..`
- `sort_by=id|group_timestamp|last_dispatch_at|next_retry_at|retry_count`
- `sort_order=asc|desc`

Each sync group response includes dispatch state metadata such as:

- `dispatch_status`
- `last_dispatch_at`
- `last_dispatch_status_code`
- `last_dispatch_error`
- `dispatched_at`
- `retry_count`
- `next_retry_at`

Dispatch status meanings:

- `pending`: the group has not been dispatched yet
- `retry_scheduled`: the last dispatch failed, but the server will retry it later
- `success`: the group was dispatched successfully
- `failed`: the dispatch failed and is not retryable
- `exhausted`: the dispatch failed repeatedly and has reached the retry limit

## Dispatch Retry Policy

Retry is scheduled only for failures that may succeed on a later attempt.

Retryable cases:

- connection failures
- request timeouts
- HTTP `502`, `503`, `504`

Non-retryable cases:

- client-side request errors such as `400`
- payload or endpoint problems that will fail again without code/data changes

Status behavior:

- retryable failures become `retry_scheduled`
- non-retryable failures become `failed`
- retryable failures that hit the retry limit become `exhausted`

Current retry schedule:

- 1st retry after 5 seconds
- 2nd retry after 15 seconds
- 3rd retry after 30 seconds

Automatic retry is handled by the server loop, and failed groups can also be retried manually through the retry endpoint.

## Reliability Goals

- remain stable under duplicate frame registration
- minimize file/DB inconsistency
- keep sync grouping deterministic
- never treat dispatch failure as success
- persist dispatch outcome and retry state for later inspection

## Documentation

- [Project Overview](docs/project.md)
- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)

## Key Files

- [`app/main.py`](app/main.py)
- [`app/routes/frames.py`](app/routes/frames.py)
- [`app/routes/sync.py`](app/routes/sync.py)
- [`app/services/frame_service.py`](app/services/frame_service.py)
- [`app/services/sync_service.py`](app/services/sync_service.py)
- [`camera_collector.py`](camera_collector.py)
- [`fake_camera_generator.py`](fake_camera_generator.py)
