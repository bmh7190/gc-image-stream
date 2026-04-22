import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")


# 필수 문자열 환경변수를 읽고 비어 있으면 예외를 발생시킨다.
def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# 필수 환경변수를 float로 변환해서 반환한다.
def get_float_env(name: str) -> float:
    raw_value = get_required_env(name)
    try:
        return float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid float value for {name}: {raw_value}") from exc


# 선택 환경변수가 있으면 float로 변환하고, 없으면 기본값을 사용한다.
def get_optional_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid float value for {name}: {raw_value}") from exc


# 선택 환경변수가 있으면 int로 변환하고, 없으면 기본값을 사용한다.
def get_optional_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid int value for {name}: {raw_value}") from exc


# 선택 환경변수가 있으면 bool로 변환하고, 없으면 기본값을 사용한다.
def get_optional_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise RuntimeError(f"Invalid bool value for {name}: {raw_value}")


# 선택 환경변수가 있으면 콤마로 구분된 문자열 목록으로 변환한다.
def get_optional_csv_env(name: str, default: list[str] | None = None) -> list[str]:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return list(default or [])

    return [
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    ]
