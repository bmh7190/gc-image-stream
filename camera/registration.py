import time
from queue import Empty, Queue
from threading import Event, Thread

import httpx

from camera.config import CollectorConfig
from camera.experiments import ExperimentRecorder


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
