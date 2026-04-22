from queue import Empty, Queue
from threading import Event, Thread

from camera.collector.config import CollectorConfig
from camera.collector.experiments import ExperimentRecorder


LEGACY_DIRECT_RELAY_NOTE = (
    "Collector direct relay is a transitional fallback. "
    "Use StreamRelayService for the primary Stream Server processing path."
)


def legacy_direct_relay_worker(
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
            "[LEGACY DIRECT RELAY CLOSED] "
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
        print(f"[LEGACY DIRECT RELAY ERROR] error={exc}")
        if experiment_recorder is not None:
            experiment_recorder.record_relay_error(str(exc))
    finally:
        channel.close()


def start_legacy_direct_relay_worker(
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
        target=legacy_direct_relay_worker,
        args=(stop_event, relay_queue, config, experiment_recorder),
        daemon=True,
    )
    worker.start()
    return relay_queue, stop_event, worker


def stop_legacy_direct_relay_runtime(
    stop_event: Event | None,
    relay_queue: Queue[dict] | None,
    worker: Thread | None,
):
    if stop_event is None or relay_queue is None or worker is None:
        return

    stop_event.set()
    relay_queue.join()
    worker.join(timeout=2.0)


def enqueue_legacy_direct_relay(
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


# Backward-compatible aliases for older standalone collector imports.
relay_worker = legacy_direct_relay_worker
start_relay_worker = start_legacy_direct_relay_worker
stop_relay_runtime = stop_legacy_direct_relay_runtime
enqueue_relay = enqueue_legacy_direct_relay
