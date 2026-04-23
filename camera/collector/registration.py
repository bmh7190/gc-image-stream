import time
from queue import Empty, Queue
from threading import Event, Thread

import httpx

from camera.collector.config import CollectorConfig
from camera.collector.experiments import ExperimentRecorder


LEGACY_HTTP_REGISTER_NOTE = (
    "Standalone collector HTTP registration is a transitional fallback. "
    "Primary Stream Server registration happens through ingest_frame()."
)


def register_legacy_frame_to_server(
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


def legacy_register_worker(
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
                response = register_legacy_frame_to_server(
                    session=session,
                    register_api_url=config.legacy_register_api_url,
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
                        "[LEGACY REGISTERED] "
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
                        "[LEGACY REGISTER FAILED] "
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
                    "[LEGACY REGISTER ERROR] "
                    f"timestamp={item['timestamp']} "
                    f"elapsed={elapsed:.3f}s "
                    f"error={exc}"
                )
            finally:
                register_queue.task_done()
    finally:
        session.close()


def start_legacy_register_worker(
    config: CollectorConfig,
    experiment_recorder: ExperimentRecorder | None = None,
):
    register_queue: Queue[dict] = Queue()
    stop_event = Event()
    worker = Thread(
        target=legacy_register_worker,
        args=(stop_event, register_queue, config, experiment_recorder),
        daemon=True,
    )
    worker.start()
    return register_queue, stop_event, worker


def stop_legacy_register_runtime(
    stop_event: Event,
    register_queue: Queue[dict],
    worker: Thread,
):
    stop_event.set()
    register_queue.join()
    worker.join(timeout=2.0)


def enqueue_legacy_registration(
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


# Backward-compatible aliases for older standalone collector imports.
register_to_server = register_legacy_frame_to_server
register_worker = legacy_register_worker
start_register_worker = start_legacy_register_worker
stop_register_runtime = stop_legacy_register_runtime
enqueue_registration = enqueue_legacy_registration
