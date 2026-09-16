import logging

from fastapi import FastAPI
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal
from app.routers import calculator, fixtures

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oddsapp")

app = FastAPI(title="Soccer Odds Analysis")
app.include_router(fixtures.router)
app.include_router(calculator.router)


@app.get("/health")
def health() -> dict:
    db_ok = False
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception:
        logger.exception("DB health check failed")
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


@app.on_event("startup")
def on_startup() -> None:
    if settings.enable_scheduler:
        from app.services.scheduler import start_scheduler

        start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if settings.enable_scheduler:
        from app.services.scheduler import shutdown_scheduler

        shutdown_scheduler()
