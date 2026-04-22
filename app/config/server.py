from app.config.env import (
    get_optional_bool_env,
    get_optional_float_env,
    get_optional_int_env,
    get_required_env,
)


DATABASE_URL = get_required_env("DATABASE_URL")
STORAGE_DIR = get_required_env("STORAGE_DIR")
PROCESSING_SERVER_URL = get_required_env("PROCESSING_SERVER_URL")
AUTO_SYNC_ENABLED = get_optional_bool_env("AUTO_SYNC_ENABLED", False)
FRAME_MAINTENANCE_INTERVAL_SEC = get_optional_float_env(
    "FRAME_MAINTENANCE_INTERVAL_SEC",
    60.0,
)
FRAME_COMPRESS_AFTER_SEC = get_optional_float_env(
    "FRAME_COMPRESS_AFTER_SEC",
    300.0,
)
FRAME_COMPRESS_JPEG_QUALITY = get_optional_int_env(
    "FRAME_COMPRESS_JPEG_QUALITY",
    60,
)
FRAME_COMPRESS_BATCH_SIZE = get_optional_int_env(
    "FRAME_COMPRESS_BATCH_SIZE",
    100,
)
