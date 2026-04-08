import os
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
DEFAULT_STREAM_TIMEOUT_SEC = 10.0
DEFAULT_REGISTER_TIMEOUT_SEC = 5.0


@dataclass(frozen=True)
class CollectorConfig:
    camera_name: str
    source_url: str
    collect_interval_sec: float
    storage_dir: str
    register_api_url: str
    capture_timeout_sec: float
    register_timeout_sec: float


# 환경 파일을 읽어서 수집기 설정을 준비한다.
def load_env_file(env_file: str | None = None):
    target = env_file or ".env"
    load_dotenv(target)
    print(f"[ENV] loaded: {target}")


# 공통 환경변수로부터 수집기 설정 객체를 만든다.
def build_collector_config(
    source_env_name: str,
    timeout_env_name: str,
    default_capture_timeout_sec: float,
) -> CollectorConfig:
    camera_name = os.getenv("CAMERA_NAME")
    source_url = os.getenv(source_env_name)

    missing = []
    if not camera_name:
        missing.append("CAMERA_NAME")
    if not source_url:
        missing.append(source_env_name)
    if missing:
        raise ValueError(f"Missing env values: {', '.join(missing)}")

    collect_interval_sec = float(
        os.getenv("COLLECT_INTERVAL_SEC", str(DEFAULT_INTERVAL_SEC))
    )
    if collect_interval_sec <= 0:
        raise ValueError("COLLECT_INTERVAL_SEC must be greater than 0")

    return CollectorConfig(
        camera_name=camera_name,
        source_url=source_url,
        collect_interval_sec=collect_interval_sec,
        storage_dir=os.getenv("STORAGE_DIR", DEFAULT_STORAGE_DIR),
        register_api_url=os.getenv("REGISTER_API_URL", DEFAULT_REGISTER_API_URL),
        capture_timeout_sec=float(
            os.getenv(timeout_env_name, str(default_capture_timeout_sec))
        ),
        register_timeout_sec=float(
            os.getenv("REGISTER_TIMEOUT_SEC", str(DEFAULT_REGISTER_TIMEOUT_SEC))
        ),
    )


# 저장 경로가 없으면 생성한다.
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


# 카메라명과 timestamp 기준으로 저장 경로를 만든다.
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


# 목표 주기를 기준으로 다음 캡처 시각을 계산한다.
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


# 이미지 바이트를 파일로 저장한다.
def save_image(save_path: str, image_bytes: bytes):
    with open(save_path, "wb") as file_obj:
        file_obj.write(image_bytes)


# 프레임 메타데이터를 서버에 등록한다.
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

    return session.post(register_api_url, data=data, timeout=timeout_sec)


# 백그라운드에서 등록 큐를 소비하며 서버 등록을 처리한다.
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


# 등록 worker 실행에 필요한 큐와 스레드를 시작한다.
def start_register_worker(config: CollectorConfig):
    register_queue: Queue[dict] = Queue()
    stop_event = Event()
    worker = Thread(
        target=register_worker,
        args=(stop_event, register_queue, config),
        daemon=True,
    )
    worker.start()
    return register_queue, stop_event, worker


# 등록 worker를 안전하게 종료한다.
def stop_register_runtime(stop_event: Event, register_queue: Queue[dict], worker: Thread):
    stop_event.set()
    register_queue.join()
    worker.join(timeout=2.0)


# 저장된 프레임을 등록 큐에 넣는다.
def enqueue_registration(
    register_queue: Queue[dict],
    camera_name: str,
    timestamp_ms: int,
    save_path: str,
):
    register_queue.put(
        {
            "device_id": camera_name,
            "timestamp": timestamp_ms,
            "file_path": save_path,
        }
    )


# 캡처 성능 로그를 한 줄로 남긴다.
def log_capture(
    timestamp_ms: int,
    capture_label: str,
    capture_elapsed: float,
    save_elapsed: float,
    cycle_elapsed: float,
    queue_size: int,
    scheduled_at: float,
    captured_at: float,
):
    offset_ms = max(0.0, (captured_at - scheduled_at) * 1000)

    print(
        "[CAPTURED] "
        f"timestamp={timestamp_ms} "
        f"{capture_label}={capture_elapsed:.3f}s "
        f"save={save_elapsed:.3f}s "
        f"cycle={cycle_elapsed:.3f}s "
        f"offset_ms={offset_ms:.1f} "
        f"queue={queue_size}"
    )


# 주기 지연 여부를 기록하고 다음 캡처 시각을 반환한다.
def log_schedule_lag(
    scheduled_at: float,
    interval_sec: float,
    loop_started_at: float,
    loop_finished_at: float,
) -> float:
    adjusted_next_capture_at = calculate_next_capture_at(
        scheduled_at=scheduled_at,
        interval_sec=interval_sec,
        now=loop_finished_at,
    )

    if adjusted_next_capture_at > scheduled_at + interval_sec:
        skipped = int(
            round(
                (
                    adjusted_next_capture_at
                    - (scheduled_at + interval_sec)
                )
                / interval_sec
            )
        )
        if skipped > 0:
            print(
                "[SCHEDULE LAG] "
                f"skipped={skipped} "
                f"loop={(loop_finished_at - loop_started_at):.3f}s"
            )

    return adjusted_next_capture_at
