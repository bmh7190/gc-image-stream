import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, Queue
from threading import Event, Lock, Thread

import httpx
from dotenv import load_dotenv


DEFAULT_INTERVAL_SEC = 1.0
DEFAULT_STORAGE_DIR = "storage"
DEFAULT_REGISTER_API_URL = "http://127.0.0.1:8000/frames/register"
DEFAULT_SNAPSHOT_TIMEOUT_SEC = 5.0
DEFAULT_STREAM_TIMEOUT_SEC = 10.0
DEFAULT_REGISTER_TIMEOUT_SEC = 5.0
DEFAULT_EXPERIMENT_LOG_DIR = "experiment_logs"


@dataclass(frozen=True)
class CollectorConfig:
    camera_name: str
    source_url: str
    collect_interval_sec: float
    storage_dir: str
    register_api_url: str
    capture_timeout_sec: float
    register_timeout_sec: float
    grpc_relay_target: str | None
    grpc_relay_timeout_sec: float | None
    experiment_log_dir: str | None
    experiment_id: str | None


class ExperimentRecorder:
    def __init__(
        self,
        config: CollectorConfig,
        collector_type: str,
    ):
        if not config.experiment_log_dir:
            raise ValueError("experiment_log_dir is required")

        self.config = config
        self.collector_type = collector_type
        self.started_at_monotonic = time.monotonic()
        self.started_at_ms = int(time.time() * 1000)
        self.run_id = sanitize_experiment_id(
            config.experiment_id
            or f"{config.camera_name}-{collector_type}-{self.started_at_ms}"
        )
        self.run_dir = os.path.join(config.experiment_log_dir, self.run_id)
        ensure_dir(self.run_dir)
        self.events_path = os.path.join(self.run_dir, "events.jsonl")
        self.summary_path = os.path.join(self.run_dir, "summary.json")
        self.lock = Lock()
        self.events_file = open(self.events_path, "a", encoding="utf-8")
        self.summary = {
            "experiment_id": self.run_id,
            "collector_type": collector_type,
            "camera_name": config.camera_name,
            "source_url": config.source_url,
            "collect_interval_sec": config.collect_interval_sec,
            "register_api_url": config.register_api_url,
            "grpc_relay_target": config.grpc_relay_target,
            "storage_dir": config.storage_dir,
            "started_at_ms": self.started_at_ms,
            "ended_at_ms": None,
            "duration_s": 0.0,
            "captured_count": 0,
            "registered_count": 0,
            "register_failed_count": 0,
            "register_error_count": 0,
            "relay_enqueued_count": 0,
            "relay_closed_count": 0,
            "relay_error_count": 0,
            "schedule_lag_count": 0,
            "schedule_lag_skipped_total": 0,
            "image_bytes_total": 0,
            "offset_ms_min": None,
            "offset_ms_max": None,
            "offset_ms_sum": 0.0,
            "offset_ms_avg": None,
            "capture_elapsed_s_sum": 0.0,
            "capture_elapsed_s_avg": None,
            "save_elapsed_s_sum": 0.0,
            "save_elapsed_s_avg": None,
        }
        self.record_event(
            "experiment_started",
            {
                "events_path": self.events_path,
                "summary_path": self.summary_path,
            },
        )

    def record_event(self, event_type: str, fields: dict | None = None):
        payload = {
            "event": event_type,
            "wall_time_ms": int(time.time() * 1000),
            "runtime_s": round(time.monotonic() - self.started_at_monotonic, 6),
        }
        if fields:
            payload.update(fields)

        with self.lock:
            self.events_file.write(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
            self.events_file.flush()

    def record_capture(
        self,
        timestamp_ms: int,
        sequence: int,
        capture_label: str,
        capture_elapsed: float,
        save_elapsed: float,
        cycle_elapsed: float,
        queue_size: int,
        scheduled_at: float,
        captured_at: float,
        image_bytes_size: int,
    ):
        offset_ms = max(0.0, (captured_at - scheduled_at) * 1000)

        with self.lock:
            self.summary["captured_count"] += 1
            self.summary["image_bytes_total"] += image_bytes_size
            self.summary["offset_ms_sum"] += offset_ms
            self.summary["capture_elapsed_s_sum"] += capture_elapsed
            self.summary["save_elapsed_s_sum"] += save_elapsed

            if self.summary["offset_ms_min"] is None:
                self.summary["offset_ms_min"] = offset_ms
            else:
                self.summary["offset_ms_min"] = min(
                    self.summary["offset_ms_min"],
                    offset_ms,
                )

            if self.summary["offset_ms_max"] is None:
                self.summary["offset_ms_max"] = offset_ms
            else:
                self.summary["offset_ms_max"] = max(
                    self.summary["offset_ms_max"],
                    offset_ms,
                )

        self.record_event(
            "captured",
            {
                "timestamp_ms": timestamp_ms,
                "sequence": sequence,
                "capture_label": capture_label,
                "capture_elapsed_s": round(capture_elapsed, 6),
                "save_elapsed_s": round(save_elapsed, 6),
                "cycle_elapsed_s": round(cycle_elapsed, 6),
                "offset_ms": round(offset_ms, 3),
                "register_queue_size": queue_size,
                "image_bytes": image_bytes_size,
            },
        )

    def record_registration(
        self,
        status: str,
        timestamp_ms: int,
        elapsed: float,
        queue_size: int,
        status_code: int | None = None,
        error: str | None = None,
    ):
        with self.lock:
            if status == "registered":
                self.summary["registered_count"] += 1
            elif status == "register_failed":
                self.summary["register_failed_count"] += 1
            elif status == "register_error":
                self.summary["register_error_count"] += 1

        self.record_event(
            status,
            {
                "timestamp_ms": timestamp_ms,
                "elapsed_s": round(elapsed, 6),
                "queue_size": queue_size,
                "status_code": status_code,
                "error": error,
            },
        )

    def record_relay_enqueued(
        self,
        timestamp_ms: int,
        sequence: int,
        image_bytes_size: int,
        queue_size: int,
    ):
        with self.lock:
            self.summary["relay_enqueued_count"] += 1

        self.record_event(
            "relay_enqueued",
            {
                "timestamp_ms": timestamp_ms,
                "sequence": sequence,
                "image_bytes": image_bytes_size,
                "relay_queue_size": queue_size,
            },
        )

    def record_relay_closed(self, success: bool, received_count: int, message: str):
        with self.lock:
            self.summary["relay_closed_count"] += 1

        self.record_event(
            "relay_closed",
            {
                "success": success,
                "received_count": received_count,
                "message": message,
            },
        )

    def record_relay_error(self, error: str):
        with self.lock:
            self.summary["relay_error_count"] += 1

        self.record_event("relay_error", {"error": error})

    def record_schedule_lag(
        self,
        skipped: int,
        loop_elapsed: float,
    ):
        with self.lock:
            self.summary["schedule_lag_count"] += 1
            self.summary["schedule_lag_skipped_total"] += skipped

        self.record_event(
            "schedule_lag",
            {
                "skipped": skipped,
                "loop_elapsed_s": round(loop_elapsed, 6),
            },
        )

    def close(self):
        ended_at_ms = int(time.time() * 1000)
        duration_s = time.monotonic() - self.started_at_monotonic

        with self.lock:
            self.summary["ended_at_ms"] = ended_at_ms
            self.summary["duration_s"] = round(duration_s, 6)

            captured_count = self.summary["captured_count"]
            if captured_count:
                self.summary["offset_ms_avg"] = (
                    self.summary["offset_ms_sum"] / captured_count
                )
                self.summary["capture_elapsed_s_avg"] = (
                    self.summary["capture_elapsed_s_sum"] / captured_count
                )
                self.summary["save_elapsed_s_avg"] = (
                    self.summary["save_elapsed_s_sum"] / captured_count
                )
                self.summary["average_fps"] = (
                    captured_count / duration_s if duration_s > 0 else 0.0
                )
            else:
                self.summary["average_fps"] = 0.0

            summary_payload = dict(self.summary)

        self.record_event(
            "experiment_finished",
            {
                "duration_s": summary_payload["duration_s"],
                "captured_count": summary_payload["captured_count"],
                "registered_count": summary_payload["registered_count"],
                "relay_enqueued_count": summary_payload["relay_enqueued_count"],
            },
        )

        with self.lock:
            self.events_file.close()

        with open(self.summary_path, "w", encoding="utf-8") as summary_file:
            json.dump(
                summary_payload,
                summary_file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )


def sanitize_experiment_id(value: str) -> str:
    sanitized = []
    for char in value:
        if char.isalnum() or char in ("-", "_"):
            sanitized.append(char)
        else:
            sanitized.append("-")

    result = "".join(sanitized).strip("-")
    return result or "experiment"


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

    relay_timeout_raw = os.getenv("GRPC_RELAY_TIMEOUT_SEC")
    relay_timeout_sec = None
    if relay_timeout_raw and relay_timeout_raw.strip():
        parsed_relay_timeout = float(relay_timeout_raw)
        if parsed_relay_timeout > 0:
            relay_timeout_sec = parsed_relay_timeout

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
        grpc_relay_target=os.getenv("GRPC_RELAY_TARGET"),
        grpc_relay_timeout_sec=relay_timeout_sec,
        experiment_log_dir=os.getenv(
            "EXPERIMENT_LOG_DIR",
            DEFAULT_EXPERIMENT_LOG_DIR,
        ),
        experiment_id=os.getenv("EXPERIMENT_ID"),
    )


def start_experiment_recorder(
    config: CollectorConfig,
    collector_type: str,
) -> ExperimentRecorder | None:
    if not config.experiment_log_dir:
        return None

    recorder = ExperimentRecorder(config, collector_type)
    print(f"[EXPERIMENT] events={recorder.events_path}")
    print(f"[EXPERIMENT] summary={recorder.summary_path}")
    return recorder


def close_experiment_recorder(recorder: ExperimentRecorder | None):
    if recorder is None:
        return

    recorder.close()
    print(f"[EXPERIMENT SAVED] summary={recorder.summary_path}")


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
    experiment_recorder: ExperimentRecorder | None = None,
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
                    if experiment_recorder is not None:
                        experiment_recorder.record_registration(
                            status="registered",
                            timestamp_ms=item["timestamp"],
                            elapsed=elapsed,
                            queue_size=register_queue.qsize(),
                            status_code=response.status_code,
                        )
                    print(
                        "[REGISTERED] "
                        f"timestamp={item['timestamp']} "
                        f"elapsed={elapsed:.3f}s "
                        f"queue={register_queue.qsize()}"
                    )
                else:
                    if experiment_recorder is not None:
                        experiment_recorder.record_registration(
                            status="register_failed",
                            timestamp_ms=item["timestamp"],
                            elapsed=elapsed,
                            queue_size=register_queue.qsize(),
                            status_code=response.status_code,
                            error=response.text,
                        )
                    print(
                        "[REGISTER FAILED] "
                        f"timestamp={item['timestamp']} "
                        f"status={response.status_code} "
                        f"elapsed={elapsed:.3f}s "
                        f"body={response.text}"
                    )
            except Exception as exc:
                elapsed = time.monotonic() - started_at
                if experiment_recorder is not None:
                    experiment_recorder.record_registration(
                        status="register_error",
                        timestamp_ms=item["timestamp"],
                        elapsed=elapsed,
                        queue_size=register_queue.qsize(),
                        error=str(exc),
                    )
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
def start_register_worker(
    config: CollectorConfig,
    experiment_recorder: ExperimentRecorder | None = None,
):
    register_queue: Queue[dict] = Queue()
    stop_event = Event()
    worker = Thread(
        target=register_worker,
        args=(stop_event, register_queue, config, experiment_recorder),
        daemon=True,
    )
    worker.start()
    return register_queue, stop_event, worker


# gRPC relay worker가 큐에서 프레임을 꺼내 processing server로 stream 전송한다.
def relay_worker(
    stop_event: Event,
    relay_queue: Queue[dict],
    config: CollectorConfig,
    experiment_recorder: ExperimentRecorder | None = None,
):
    try:
        import grpc
    except ImportError as exc:
        raise RuntimeError(
            "grpcio is required when GRPC_RELAY_TARGET is set"
        ) from exc

    from processing.grpc_relay import RelayFrame, build_frame_relay_stub

    def relay_frames():
        while not stop_event.is_set() or not relay_queue.empty():
            try:
                item = relay_queue.get(timeout=0.5)
            except Empty:
                continue

            try:
                yield RelayFrame(
                    device_id=item["device_id"],
                    timestamp_ms=item["timestamp"],
                    sequence=item["sequence"],
                    content_type=item["content_type"],
                    image_bytes=item["image_bytes"],
                    file_path=item["file_path"],
                )
            finally:
                relay_queue.task_done()

    channel = grpc.insecure_channel(config.grpc_relay_target)
    stub = build_frame_relay_stub(channel)

    try:
        ack = stub(
            relay_frames(),
            timeout=config.grpc_relay_timeout_sec,
        )
        print(
            "[RELAY CLOSED] "
            f"success={ack.success} "
            f"received={ack.received_count} "
            f"message={ack.message}"
        )
        if experiment_recorder is not None:
            experiment_recorder.record_relay_closed(
                success=ack.success,
                received_count=ack.received_count,
                message=ack.message,
            )
    except Exception as exc:
        print(f"[RELAY ERROR] error={exc}")
        if experiment_recorder is not None:
            experiment_recorder.record_relay_error(str(exc))
    finally:
        channel.close()


# relay target이 있으면 gRPC relay worker를 시작한다.
def start_relay_worker(
    config: CollectorConfig,
    experiment_recorder: ExperimentRecorder | None = None,
):
    if not config.grpc_relay_target:
        return None, None, None

    try:
        import grpc  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "grpcio is required when GRPC_RELAY_TARGET is set"
        ) from exc

    relay_queue: Queue[dict] = Queue()
    stop_event = Event()
    worker = Thread(
        target=relay_worker,
        args=(stop_event, relay_queue, config, experiment_recorder),
        daemon=True,
    )
    worker.start()
    return relay_queue, stop_event, worker


# 등록 worker를 안전하게 종료한다.
def stop_register_runtime(stop_event: Event, register_queue: Queue[dict], worker: Thread):
    stop_event.set()
    register_queue.join()
    worker.join(timeout=2.0)


# relay worker를 안전하게 종료한다.
def stop_relay_runtime(stop_event: Event | None, relay_queue: Queue[dict] | None, worker: Thread | None):
    if stop_event is None or relay_queue is None or worker is None:
        return

    stop_event.set()
    relay_queue.join()
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


# relay 대상 프레임을 큐에 넣는다.
def enqueue_relay(
    relay_queue: Queue[dict] | None,
    camera_name: str,
    timestamp_ms: int,
    sequence: int,
    image_bytes: bytes,
    save_path: str,
    experiment_recorder: ExperimentRecorder | None = None,
):
    if relay_queue is None:
        return

    relay_queue.put(
        {
            "device_id": camera_name,
            "timestamp": timestamp_ms,
            "sequence": sequence,
            "content_type": "image/jpeg",
            "image_bytes": image_bytes,
            "file_path": save_path,
        }
    )
    if experiment_recorder is not None:
        experiment_recorder.record_relay_enqueued(
            timestamp_ms=timestamp_ms,
            sequence=sequence,
            image_bytes_size=len(image_bytes),
            queue_size=relay_queue.qsize(),
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
    runtime_elapsed: float,
):
    offset_ms = max(0.0, (captured_at - scheduled_at) * 1000)

    print(
        "[CAPTURED] "
        f"runtime_s={runtime_elapsed:.3f} "
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
    runtime_elapsed: float,
    experiment_recorder: ExperimentRecorder | None = None,
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
            loop_elapsed = loop_finished_at - loop_started_at
            print(
                "[SCHEDULE LAG] "
                f"runtime_s={runtime_elapsed:.3f} "
                f"skipped={skipped} "
                f"loop={loop_elapsed:.3f}s"
            )
            if experiment_recorder is not None:
                experiment_recorder.record_schedule_lag(
                    skipped=skipped,
                    loop_elapsed=loop_elapsed,
                )

    return adjusted_next_capture_at
