import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, Queue
from threading import Event, Thread

import httpx
from dotenv import load_dotenv


DEFAULT_INTERVAL_SEC = 1.0
DEFAULT_STORAGE_DIR = "storage"
DEFAULT_REGISTER_API_URL = "http://127.0.0.1:8000/frames/register"
DEFAULT_SNAPSHOT_TIMEOUT_SEC = 5.0
DEFAULT_REGISTER_TIMEOUT_SEC = 5.0


@dataclass(frozen=True)
class CollectorConfig:
    camera_name: str
    camera_snapshot_url: str
    collect_interval_sec: float
    storage_dir: str
    register_api_url: str
    snapshot_timeout_sec: float
    register_timeout_sec: float


def load_env_file(env_file: str | None = None):
    target = env_file or ".env"
    load_dotenv(target)
    print(f"[ENV] loaded: {target}")


def build_config() -> CollectorConfig:
    camera_name = os.getenv("CAMERA_NAME")
    camera_snapshot_url = os.getenv("CAMERA_SNAPSHOT_URL")

    missing = []
    if not camera_name:
        missing.append("CAMERA_NAME")
    if not camera_snapshot_url:
        missing.append("CAMERA_SNAPSHOT_URL")
    if missing:
        raise ValueError(f"Missing env values: {', '.join(missing)}")

    collect_interval_sec = float(
        os.getenv("COLLECT_INTERVAL_SEC", str(DEFAULT_INTERVAL_SEC))
    )
    if collect_interval_sec <= 0:
        raise ValueError("COLLECT_INTERVAL_SEC must be greater than 0")

    return CollectorConfig(
        camera_name=camera_name,
        camera_snapshot_url=camera_snapshot_url,
        collect_interval_sec=collect_interval_sec,
        storage_dir=os.getenv("STORAGE_DIR", DEFAULT_STORAGE_DIR),
        register_api_url=os.getenv("REGISTER_API_URL", DEFAULT_REGISTER_API_URL),
        snapshot_timeout_sec=float(
            os.getenv("SNAPSHOT_TIMEOUT_SEC", str(DEFAULT_SNAPSHOT_TIMEOUT_SEC))
        ),
        register_timeout_sec=float(
            os.getenv("REGISTER_TIMEOUT_SEC", str(DEFAULT_REGISTER_TIMEOUT_SEC))
        ),
    )


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def build_save_path(camera_name: str, timestamp_ms: int, base_dir: str) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000)

    folder = os.path.join(
        base_dir,
        camera_name,
        str(dt.year),
        f"{dt.month:02d}",
        f"{dt.day:02d}",
    )
    ensure_dir(folder)

    filename = f"{camera_name}_{timestamp_ms}.jpg"
    return os.path.join(folder, filename)


def calculate_next_capture_at(
    scheduled_at: float,
    interval_sec: float,
    now: float,
) -> float:
    next_capture_at = scheduled_at + interval_sec
    if next_capture_at > now:
        return next_capture_at

    missed_intervals = int((now - next_capture_at) // interval_sec) + 1
    return next_capture_at + (missed_intervals * interval_sec)


def download_image(
    session: httpx.Client,
    url: str,
    timeout_sec: float,
) -> bytes:
    response = session.get(url, timeout=timeout_sec)
    response.raise_for_status()
    return response.content


def register_to_server(
    session: httpx.Client,
    register_api_url: str,
    device_id: str,
    timestamp: int,
    file_path: str,
    timeout_sec: float,
):
    data = {
        "device_id": device_id,
        "timestamp": str(timestamp),
        "file_path": file_path,
    }

    response = session.post(register_api_url, data=data, timeout=timeout_sec)
    return response


def register_worker(
    stop_event: Event,
    register_queue: Queue[dict],
    config: CollectorConfig,
):
    session = httpx.Client()

    try:
        while not stop_event.is_set() or not register_queue.empty():
            try:
                item = register_queue.get(timeout=0.5)
            except Empty:
                continue

            started_at = time.monotonic()
            try:
                response = register_to_server(
                    session=session,
                    register_api_url=config.register_api_url,
                    device_id=item["device_id"],
                    timestamp=item["timestamp"],
                    file_path=item["file_path"],
                    timeout_sec=config.register_timeout_sec,
                )

                elapsed = time.monotonic() - started_at
                if response.status_code == 200:
                    print(
                        "[REGISTERED] "
                        f"timestamp={item['timestamp']} "
                        f"elapsed={elapsed:.3f}s "
                        f"queue={register_queue.qsize()}"
                    )
                else:
                    print(
                        "[REGISTER FAILED] "
                        f"timestamp={item['timestamp']} "
                        f"status={response.status_code} "
                        f"elapsed={elapsed:.3f}s "
                        f"body={response.text}"
                    )
            except Exception as exc:
                elapsed = time.monotonic() - started_at
                print(
                    "[REGISTER ERROR] "
                    f"timestamp={item['timestamp']} "
                    f"elapsed={elapsed:.3f}s "
                    f"error={exc}"
                )
            finally:
                register_queue.task_done()
    finally:
        session.close()


def save_image(save_path: str, image_bytes: bytes):
    with open(save_path, "wb") as file_obj:
        file_obj.write(image_bytes)


def main():
    env_file = sys.argv[1] if len(sys.argv) > 1 else None
    load_env_file(env_file)
    config = build_config()

    print(f"[START] collecting from {config.camera_name}")
    print(f"[URL] {config.camera_snapshot_url}")
    print(f"[INTERVAL] target={config.collect_interval_sec:.3f}s")
    print(f"[REGISTER API] {config.register_api_url}")
    print(f"[STORAGE DIR] {config.storage_dir}")

    register_queue: Queue[dict] = Queue()
    stop_event = Event()
    worker = Thread(
        target=register_worker,
        args=(stop_event, register_queue, config),
        daemon=True,
    )
    worker.start()

    snapshot_session = httpx.Client()
    next_capture_at = time.monotonic()

    try:
        while True:
            sleep_sec = max(0.0, next_capture_at - time.monotonic())
            if sleep_sec > 0:
                time.sleep(sleep_sec)

            scheduled_at = next_capture_at
            request_started_at = time.monotonic()

            try:
                image_bytes = download_image(
                    session=snapshot_session,
                    url=config.camera_snapshot_url,
                    timeout_sec=config.snapshot_timeout_sec,
                )
                downloaded_at = time.monotonic()
                timestamp_ms = int(time.time() * 1000)
                save_path = build_save_path(
                    config.camera_name,
                    timestamp_ms,
                    config.storage_dir,
                )
                save_image(save_path, image_bytes)
                saved_at = time.monotonic()

                register_queue.put(
                    {
                        "device_id": config.camera_name,
                        "timestamp": timestamp_ms,
                        "file_path": save_path,
                    }
                )

                print(
                    "[CAPTURED] "
                    f"timestamp={timestamp_ms} "
                    f"download={(downloaded_at - request_started_at):.3f}s "
                    f"save={(saved_at - downloaded_at):.3f}s "
                    f"cycle={(saved_at - request_started_at):.3f}s "
                    f"queue={register_queue.qsize()}"
                )
            except Exception as exc:
                print(f"[CAPTURE ERROR] error={exc}")

            loop_finished_at = time.monotonic()
            adjusted_next_capture_at = calculate_next_capture_at(
                scheduled_at=scheduled_at,
                interval_sec=config.collect_interval_sec,
                now=loop_finished_at,
            )

            if adjusted_next_capture_at > scheduled_at + config.collect_interval_sec:
                skipped = int(
                    round(
                        (
                            adjusted_next_capture_at
                            - (scheduled_at + config.collect_interval_sec)
                        )
                        / config.collect_interval_sec
                    )
                )
                if skipped > 0:
                    print(
                        "[SCHEDULE LAG] "
                        f"skipped={skipped} "
                        f"loop={(loop_finished_at - request_started_at):.3f}s"
                    )

            next_capture_at = adjusted_next_capture_at
    except KeyboardInterrupt:
        print("[STOP] shutting down collector")
    finally:
        snapshot_session.close()
        stop_event.set()
        register_queue.join()
        worker.join(timeout=2.0)


if __name__ == "__main__":
    main()
