import sys
import time

import httpx

from camera.core import (
    DEFAULT_SNAPSHOT_TIMEOUT_SEC,
    build_collector_config,
    build_save_path,
    enqueue_registration,
    load_env_file,
    log_capture,
    log_schedule_lag,
    save_image,
    start_register_worker,
    stop_register_runtime,
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
    print(f"[REGISTER API] {config.register_api_url}")
    print(f"[STORAGE DIR] {config.storage_dir}")

    register_queue, stop_event, worker = start_register_worker(config)
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
                    url=config.source_url,
                    timeout_sec=config.capture_timeout_sec,
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

                enqueue_registration(
                    register_queue,
                    config.camera_name,
                    timestamp_ms,
                    save_path,
                )
                log_capture(
                    timestamp_ms=timestamp_ms,
                    capture_label="download",
                    capture_elapsed=downloaded_at - request_started_at,
                    save_elapsed=saved_at - downloaded_at,
                    cycle_elapsed=saved_at - request_started_at,
                    queue_size=register_queue.qsize(),
                )
            except Exception as exc:
                print(f"[CAPTURE ERROR] error={exc}")

            loop_finished_at = time.monotonic()
            next_capture_at = log_schedule_lag(
                scheduled_at=scheduled_at,
                interval_sec=config.collect_interval_sec,
                loop_started_at=request_started_at,
                loop_finished_at=loop_finished_at,
            )
    except KeyboardInterrupt:
        print("[STOP] shutting down collector")
    finally:
        snapshot_session.close()
        stop_register_runtime(stop_event, register_queue, worker)


if __name__ == "__main__":
    main()
