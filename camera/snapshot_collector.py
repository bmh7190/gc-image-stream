import sys
import time

import httpx

from camera.collector import (
    DEFAULT_SNAPSHOT_TIMEOUT_SEC,
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


# snapshot collector용 설정을 만든다.
def build_config():
    return build_collector_config(
        source_env_name="CAMERA_SNAPSHOT_URL",
        timeout_env_name="SNAPSHOT_TIMEOUT_SEC",
        default_capture_timeout_sec=DEFAULT_SNAPSHOT_TIMEOUT_SEC,
    )


# snapshot URL에서 이미지 한 장을 내려받는다.
def download_image(
    session: httpx.Client,
    url: str,
    timeout_sec: float,
) -> bytes:
    response = session.get(url, timeout=timeout_sec)
    response.raise_for_status()
    return response.content


# snapshot 기반 수집 루프를 실행한다.
def main():
    env_file = sys.argv[1] if len(sys.argv) > 1 else None
    load_env_file(env_file)
    config = build_config()

    print(f"[START] collecting from {config.camera_name}")
    print(f"[URL] {config.source_url}")
    print(f"[INTERVAL] target={config.collect_interval_sec:.3f}s")
    print(f"[LEGACY REGISTER API] {config.legacy_register_api_url}")
    if config.legacy_grpc_relay_target:
        print(f"[LEGACY GRPC RELAY] {config.legacy_grpc_relay_target}")
    print(f"[LEGACY STORAGE DIR] {config.legacy_storage_dir}")

    experiment_recorder = start_experiment_recorder(config, "snapshot")
    register_queue, stop_event, worker = start_legacy_register_worker(
        config,
        experiment_recorder,
    )
    relay_queue, relay_stop_event, relay_worker = start_legacy_direct_relay_worker(
        config,
        experiment_recorder,
    )
    snapshot_session = httpx.Client()
    started_at = time.monotonic()
    next_capture_at = time.monotonic()
    sequence = 0

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
                    url=config.source_url,
                    timeout_sec=config.capture_timeout_sec,
                )
                downloaded_at = time.monotonic()
                timestamp_ms = int(time.time() * 1000)
                save_path = build_legacy_collector_save_path(
                    config.camera_name,
                    timestamp_ms,
                    config.legacy_storage_dir,
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
                    capture_label="download",
                    capture_elapsed=downloaded_at - request_started_at,
                    save_elapsed=saved_at - downloaded_at,
                    cycle_elapsed=saved_at - request_started_at,
                    queue_size=register_queue.qsize(),
                    scheduled_at=scheduled_at,
                    captured_at=downloaded_at,
                    runtime_elapsed=saved_at - started_at,
                )
                if experiment_recorder is not None:
                    experiment_recorder.record_capture(
                        timestamp_ms=timestamp_ms,
                        sequence=sequence,
                        capture_label="download",
                        capture_elapsed=downloaded_at - request_started_at,
                        save_elapsed=saved_at - downloaded_at,
                        cycle_elapsed=saved_at - request_started_at,
                        queue_size=register_queue.qsize(),
                        scheduled_at=scheduled_at,
                        captured_at=downloaded_at,
                        image_bytes_size=len(image_bytes),
                    )
            except Exception as exc:
                print(f"[CAPTURE ERROR] error={exc}")

            loop_finished_at = time.monotonic()
            next_capture_at = log_schedule_lag(
                scheduled_at=scheduled_at,
                interval_sec=config.collect_interval_sec,
                loop_started_at=request_started_at,
                loop_finished_at=loop_finished_at,
                runtime_elapsed=loop_finished_at - started_at,
                experiment_recorder=experiment_recorder,
            )
    except KeyboardInterrupt:
        print("[STOP] shutting down collector")
    finally:
        snapshot_session.close()
        stop_legacy_register_runtime(stop_event, register_queue, worker)
        stop_legacy_direct_relay_runtime(relay_stop_event, relay_queue, relay_worker)
        close_experiment_recorder(experiment_recorder)


if __name__ == "__main__":
    main()
