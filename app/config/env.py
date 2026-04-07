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
