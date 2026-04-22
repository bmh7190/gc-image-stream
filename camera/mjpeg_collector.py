import sys
import time

import httpx

from camera.mjpeg_stream import extract_mjpeg_frames, iter_mjpeg_frames
from camera.collector import (
    DEFAULT_STREAM_TIMEOUT_SEC,
    build_collector_config,
    build_legacy_collector_save_path,
    close_experiment_recorder,
    enqueue_legacy_direct_relay,
    enqueue_legacy_registration,
    load_env_file,
    log_capture,
    log_schedule_lag,
    save_legacy_collector_image,
    start_experiment_recorder,
    start_legacy_direct_relay_worker,
    start_legacy_register_worker,
    stop_legacy_direct_relay_runtime,
    stop_legacy_register_runtime,
)


# MJPEG collector용 설정을 만든다.
def build_config():
    return build_collector_config(
        source_env_name="CAMERA_STREAM_URL",
        timeout_env_name="STREAM_TIMEOUT_SEC",
        default_capture_timeout_sec=DEFAULT_STREAM_TIMEOUT_SEC,
    )


# MJPEG 스트림에서 프레임을 샘플링하며 수집 루프를 실행한다.
def main():
    env_file = sys.argv[1] if len(sys.argv) > 1 else None
    load_env_file(env_file)
    config = build_config()

    print(f"[START] collecting MJPEG stream from {config.camera_name}")
    print(f"[URL] {config.source_url}")
    print(f"[INTERVAL] target={config.collect_interval_sec:.3f}s")
    print(f"[REGISTER API] {config.register_api_url}")
    if config.grpc_relay_target:
        print(f"[GRPC RELAY] {config.grpc_relay_target}")
    print(f"[STORAGE DIR] {config.storage_dir}")

    experiment_recorder = start_experiment_recorder(config, "mjpeg")
    register_queue, stop_event, worker = start_legacy_register_worker(
        config,
        experiment_recorder,
    )
    relay_queue, relay_stop_event, relay_worker = start_legacy_direct_relay_worker(
        config,
        experiment_recorder,
    )
    stream_session = httpx.Client()
    started_at = time.monotonic()
    next_capture_at = time.monotonic()
    sequence = 0
    frame_iter = iter_mjpeg_frames(
        session=stream_session,
        url=config.source_url,
        timeout_sec=config.capture_timeout_sec,
    )

    try:
        while True:
            read_started_at = time.monotonic()
            try:
                image_bytes = next(frame_iter)
            except StopIteration:
                raise RuntimeError("MJPEG stream ended unexpectedly") from None

            frame_ready_at = time.monotonic()
            if frame_ready_at < next_capture_at:
                continue

            scheduled_at = next_capture_at
            timestamp_ms = int(time.time() * 1000)
            save_path = build_legacy_collector_save_path(
                config.camera_name,
                timestamp_ms,
                config.storage_dir,
            )
            save_legacy_collector_image(save_path, image_bytes)
            saved_at = time.monotonic()

            enqueue_legacy_registration(
                register_queue,
                config.camera_name,
                timestamp_ms,
                save_path,
            )
            sequence += 1
            enqueue_legacy_direct_relay(
                relay_queue,
                config.camera_name,
                timestamp_ms,
                sequence,
                image_bytes,
                save_path,
                experiment_recorder,
            )
            log_capture(
                timestamp_ms=timestamp_ms,
                capture_label="stream",
                capture_elapsed=frame_ready_at - read_started_at,
                save_elapsed=saved_at - frame_ready_at,
                cycle_elapsed=saved_at - read_started_at,
                queue_size=register_queue.qsize(),
                scheduled_at=scheduled_at,
                captured_at=frame_ready_at,
                runtime_elapsed=saved_at - started_at,
            )
            if experiment_recorder is not None:
                experiment_recorder.record_capture(
                    timestamp_ms=timestamp_ms,
                    sequence=sequence,
                    capture_label="stream",
                    capture_elapsed=frame_ready_at - read_started_at,
                    save_elapsed=saved_at - frame_ready_at,
                    cycle_elapsed=saved_at - read_started_at,
                    queue_size=register_queue.qsize(),
                    scheduled_at=scheduled_at,
                    captured_at=frame_ready_at,
                    image_bytes_size=len(image_bytes),
                )

            next_capture_at = log_schedule_lag(
                scheduled_at=scheduled_at,
                interval_sec=config.collect_interval_sec,
                loop_started_at=read_started_at,
                loop_finished_at=saved_at,
                runtime_elapsed=saved_at - started_at,
                experiment_recorder=experiment_recorder,
            )
    except KeyboardInterrupt:
        print("[STOP] shutting down MJPEG collector")
    finally:
        stream_session.close()
        stop_legacy_register_runtime(stop_event, register_queue, worker)
        stop_legacy_direct_relay_runtime(relay_stop_event, relay_queue, relay_worker)
        close_experiment_recorder(experiment_recorder)


if __name__ == "__main__":
    main()
