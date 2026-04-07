from pathlib import Path

import pytest

from camera import core
from camera import snapshot_collector


def test_build_config_reads_required_values(monkeypatch):
    monkeypatch.setenv("CAMERA_NAME", "camera1")
    monkeypatch.setenv("CAMERA_SNAPSHOT_URL", "http://camera.local/shot.jpg")
    monkeypatch.setenv("COLLECT_INTERVAL_SEC", "0.1")
    monkeypatch.setenv("STORAGE_DIR", "captures")
    monkeypatch.setenv("REGISTER_API_URL", "http://server.local/frames/register")

    config = snapshot_collector.build_config()

    assert config.camera_name == "camera1"
    assert config.source_url == "http://camera.local/shot.jpg"
    assert config.collect_interval_sec == 0.1
    assert config.storage_dir == "captures"
    assert config.register_api_url == "http://server.local/frames/register"
    assert config.capture_timeout_sec == 5.0
    assert config.register_timeout_sec == 5.0


def test_build_config_rejects_missing_snapshot_env(monkeypatch):
    monkeypatch.delenv("CAMERA_NAME", raising=False)
    monkeypatch.delenv("CAMERA_SNAPSHOT_URL", raising=False)

    with pytest.raises(ValueError, match="CAMERA_NAME, CAMERA_SNAPSHOT_URL"):
        snapshot_collector.build_config()


def test_build_save_path_uses_camera_date_layout(tmp_path):
    path = core.build_save_path(
        camera_name="camera2",
        timestamp_ms=1712321562400,
        base_dir=str(tmp_path),
    )

    expected_dir = tmp_path / "camera2" / "2024" / "04" / "05"
    assert Path(path).parent == expected_dir
    assert Path(path).name == "camera2_1712321562400.jpg"
    assert expected_dir.is_dir()


def test_calculate_next_capture_at_skips_missed_intervals():
    next_capture_at = core.calculate_next_capture_at(
        scheduled_at=10.0,
        interval_sec=0.1,
        now=10.35,
    )

    assert next_capture_at == pytest.approx(10.4)
