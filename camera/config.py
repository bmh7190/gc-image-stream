import os
from dataclasses import dataclass

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
