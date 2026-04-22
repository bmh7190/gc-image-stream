from camera import mjpeg_collector, mjpeg_stream


def test_build_config_reads_stream_env(monkeypatch):
    monkeypatch.setenv("CAMERA_NAME", "camera1")
    monkeypatch.setenv("CAMERA_STREAM_URL", "http://camera.local/video")
    monkeypatch.setenv("COLLECT_INTERVAL_SEC", "0.1")

    config = mjpeg_collector.build_config()

    assert config.camera_name == "camera1"
    assert config.source_url == "http://camera.local/video"
    assert config.collect_interval_sec == 0.1
    assert config.capture_timeout_sec == 10.0


def test_extract_mjpeg_frames_returns_complete_jpegs():
    buffer = bytearray(
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n\r\n"
        b"\xff\xd8frame1\xff\xd9"
        b"\r\n--frame\r\n"
        b"Content-Type: image/jpeg\r\n\r\n"
        b"\xff\xd8frame2\xff\xd9"
    )

    frames = mjpeg_stream.extract_mjpeg_frames(buffer)

    assert frames == [b"\xff\xd8frame1\xff\xd9", b"\xff\xd8frame2\xff\xd9"]
    assert buffer == bytearray()


def test_extract_mjpeg_frames_keeps_incomplete_tail():
    buffer = bytearray(
        b"noise"
        b"\xff\xd8complete\xff\xd9"
        b"\xff\xd8partial"
    )

    frames = mjpeg_stream.extract_mjpeg_frames(buffer)

    assert frames == [b"\xff\xd8complete\xff\xd9"]
    assert buffer == bytearray(b"\xff\xd8partial")
