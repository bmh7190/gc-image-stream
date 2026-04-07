import sys
import time

import httpx

from camera.core import (
    DEFAULT_STREAM_TIMEOUT_SEC,
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


JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


# MJPEG collector용 설정을 만든다.
def build_config():
    return build_collector_config(
        source_env_name="CAMERA_STREAM_URL",
        timeout_env_name="STREAM_TIMEOUT_SEC",
        default_capture_timeout_sec=DEFAULT_STREAM_TIMEOUT_SEC,
    )


# 바이트 버퍼에서 완성된 JPEG 프레임만 잘라낸다.
def extract_mjpeg_frames(buffer: bytearray) -> list[bytes]:
    frames: list[bytes] = []

    while True:
        start_index = buffer.find(JPEG_SOI)
        if start_index == -1:
            buffer.clear()
            break

        end_index = buffer.find(JPEG_EOI, start_index + len(JPEG_SOI))
        if end_index == -1:
            if start_index > 0:
                del buffer[:start_index]
            break

        frame_end = end_index + len(JPEG_EOI)
        frames.append(bytes(buffer[start_index:frame_end]))
        del buffer[:frame_end]

    return frames


# MJPEG 스트림을 읽으면서 JPEG 프레임을 순서대로 꺼낸다.
def iter_mjpeg_frames(
    session: httpx.Client,
    url: str,
    timeout_sec: float,
    chunk_size: int = 65_536,
):
    buffer = bytearray()
    with session.stream("GET", url, timeout=timeout_sec) as response:
        response.raise_for_status()

        for chunk in response.iter_bytes(chunk_size=chunk_size):
            if not chunk:
                continue

            buffer.extend(chunk)
            for frame in extract_mjpeg_frames(buffer):
                yield frame


# MJPEG 스트림에서 프레임을 샘플링하며 수집 루프를 실행한다.
def main():
    env_file = sys.argv[1] if len(sys.argv) > 1 else None
    load_env_file(env_file)
    config = build_config()

    print(f"[START] collecting MJPEG stream from {config.camera_name}")
    print(f"[URL] {config.source_url}")
    print(f"[INTERVAL] target={config.collect_interval_sec:.3f}s")
    print(f"[REGISTER API] {config.register_api_url}")
    print(f"[STORAGE DIR] {config.storage_dir}")

    register_queue, stop_event, worker = start_register_worker(config)
    stream_session = httpx.Client()
    next_capture_at = time.monotonic()
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
                capture_label="stream",
                capture_elapsed=frame_ready_at - read_started_at,
                save_elapsed=saved_at - frame_ready_at,
                cycle_elapsed=saved_at - read_started_at,
                queue_size=register_queue.qsize(),
            )

            next_capture_at = log_schedule_lag(
                scheduled_at=scheduled_at,
                interval_sec=config.collect_interval_sec,
                loop_started_at=read_started_at,
                loop_finished_at=saved_at,
            )
    except KeyboardInterrupt:
        print("[STOP] shutting down MJPEG collector")
    finally:
        stream_session.close()
        stop_register_runtime(stop_event, register_queue, worker)


if __name__ == "__main__":
    main()
