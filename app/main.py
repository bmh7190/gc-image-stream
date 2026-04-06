import asyncio
from fastapi import FastAPI

from app.db import Base, engine, SessionLocal, ensure_database_schema
from app.config.server import PROCESSING_SERVER_URL
from app.routes.frames import router as frames_router
from app.routes.sync import router as sync_router
from app.services.sync_service import (
    build_sync_groups,
    dispatch_sync_group,
    get_groups_ready_for_retry,
    get_sync_group_by_id,
    record_sync_group_dispatch_result,
)

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
                print(f"[AUTO SYNC] created {len(groups)} group(s)")

            if retry_groups:
                print(f"[AUTO RETRY] retrying {len(retry_groups)} group(s)")

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
                        print(f"[AUTO DISPATCH SKIPPED] group_id={group_id} not found")
                        continue

                    result = await dispatch_sync_group(group_data, PROCESSING_SERVER_URL)
                    record_sync_group_dispatch_result(db, group_id, result)

                    if result.get("success"):
                        print(f"[AUTO DISPATCH SUCCESS] group_id={group_id}")
                    else:
                        print(
                            f"[AUTO DISPATCH FAILED] group_id={group_id}, "
                            f"error={result.get('error')}"
                        )

                except Exception as e:
                    print(f"[AUTO DISPATCH ERROR] group_id={group_id}, error={e}")

        except Exception as e:
            print(f"[AUTO SYNC ERROR] {e}")
        finally:
            db.close()

        await asyncio.sleep(AUTO_SYNC_INTERVAL_SEC)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(auto_sync_loop())
    print(
        f"[AUTO SYNC STARTED] interval={AUTO_SYNC_INTERVAL_SEC}s, "
        f"threshold={AUTO_SYNC_THRESHOLD_MS}ms, "
        f"dispatch_url={PROCESSING_SERVER_URL}"
    )


@app.get("/")
def root():
    return {"message": "GC Image Stream server is running"}
