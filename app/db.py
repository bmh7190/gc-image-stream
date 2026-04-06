from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config.server import DATABASE_URL


engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


SYNC_GROUP_SCHEMA_UPDATES = {
    "dispatch_status": (
        "ALTER TABLE sync_groups "
        "ADD COLUMN dispatch_status VARCHAR NOT NULL DEFAULT 'pending'"
    ),
    "last_dispatch_at": (
        "ALTER TABLE sync_groups "
        "ADD COLUMN last_dispatch_at BIGINT"
    ),
    "last_dispatch_status_code": (
        "ALTER TABLE sync_groups "
        "ADD COLUMN last_dispatch_status_code INTEGER"
    ),
    "last_dispatch_error": (
        "ALTER TABLE sync_groups "
        "ADD COLUMN last_dispatch_error VARCHAR"
    ),
    "dispatched_at": (
        "ALTER TABLE sync_groups "
        "ADD COLUMN dispatched_at BIGINT"
    ),
    "retry_count": (
        "ALTER TABLE sync_groups "
        "ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0"
    ),
    "next_retry_at": (
        "ALTER TABLE sync_groups "
        "ADD COLUMN next_retry_at BIGINT"
    ),
}


def ensure_database_schema():
    inspector = inspect(engine)

    if "sync_groups" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("sync_groups")
    }

    missing_updates = [
        sql
        for column_name, sql in SYNC_GROUP_SCHEMA_UPDATES.items()
        if column_name not in existing_columns
    ]

    if not missing_updates:
        return

    with engine.begin() as connection:
        for sql in missing_updates:
            connection.execute(text(sql))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
