from app.config.env import get_required_env


DATABASE_URL = get_required_env("DATABASE_URL")
STORAGE_DIR = get_required_env("STORAGE_DIR")
PROCESSING_SERVER_URL = get_required_env("PROCESSING_SERVER_URL")
