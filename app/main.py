import asyncio
import logging
from fastapi import FastAPI

from app.db import Base, engine, SessionLocal, ensure_database_schema
from app.config.server import PROCESSING_SERVER_URL
from app.logging_config import configure_logging, format_log_event
from app.routes.frames import router as frames_router
from app.routes.sync import router as sync_router
from app.services.sync_service import (
    build_sync_groups,
    dispatch_sync_group,
    get_groups_ready_for_retry,
    get_sync_group_by_id,
    record_sync_group_dispatch_result,
)

configure_logging()

logger = logging.getLogger("gc_image_stream.app")

Base.metadata.create_all(bind=engine)
ensure_database_schema()

app = FastAPI(title="GC Image Stream")

app.include_router(frames_router)
app.include_router(sync_router)

AUTO_SYNC_THRESHOLD_MS = 200
AUTO_SYNC_INTERVAL_SEC = 1.0


async def auto_sync_loop():
    while True:
        db = SessionLocal()
        try:
            groups = build_sync_groups(db, threshold_ms=AUTO_SYNC_THRESHOLD_MS)
            retry_groups = get_groups_ready_for_retry(db)

            if groups:
                logger.info(
                    format_log_event(
                        "sync_groups_created",
                        source="auto",
                        count=len(groups),
                    )
                )

            if retry_groups:
                logger.info(
                    format_log_event(
                        "sync_groups_retrying",
                        source="auto",
                        count=len(retry_groups),
                    )
                )

            dispatch_targets = [
                {"id": group.id}
                for group in groups
            ] + [
                {"id": group["id"]}
                for group in retry_groups
            ]

            for target in dispatch_targets:
                group_id = target["id"]
                try:
                    group_data = get_sync_group_by_id(db, group_id)

                    if group_data is None:
                        logger.warning(
                            format_log_event(
                                "sync_group_dispatch_skipped",
                                source="auto",
                                group_id=group_id,
                                reason="group_not_found",
                            )
                        )
                        continue

                    result = await dispatch_sync_group(group_data, PROCESSING_SERVER_URL)
                    record_sync_group_dispatch_result(db, group_id, result, source="auto")

                    if result.get("success"):
                        logger.info(
                            format_log_event(
                                "sync_group_dispatch_succeeded",
                                source="auto",
                                group_id=group_id,
                                status_code=result.get("status_code"),
                            )
                        )
                    else:
                        logger.warning(
                            format_log_event(
                                "sync_group_dispatch_failed",
                                source="auto",
                                group_id=group_id,
                                status_code=result.get("status_code"),
                                error=result.get("error"),
                            )
                        )

                except Exception as e:
                    logger.exception(
                        format_log_event(
                            "sync_group_dispatch_error",
                            source="auto",
                            group_id=group_id,
                            error=str(e),
                        )
                    )

        except Exception as e:
            logger.exception(
                format_log_event(
                    "auto_sync_loop_error",
                    error=str(e),
                )
            )
        finally:
            db.close()

        await asyncio.sleep(AUTO_SYNC_INTERVAL_SEC)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(auto_sync_loop())
    logger.info(
        format_log_event(
            "auto_sync_started",
            interval_sec=AUTO_SYNC_INTERVAL_SEC,
            threshold_ms=AUTO_SYNC_THRESHOLD_MS,
            dispatch_url=PROCESSING_SERVER_URL,
        )
    )


@app.get("/")
def root():
    return {"message": "GC Image Stream server is running"}
