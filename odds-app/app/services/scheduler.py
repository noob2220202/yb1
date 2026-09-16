"""APScheduler 기반 오즈 수집 스케줄러.

별도 워커 프로세스 없이 FastAPI 프로세스 내에서 BackgroundScheduler로 동작한다.

- 전체 수집: ingest_interval_minutes(기본 15분)마다 fixture 목록 + 전체 오즈 수집.
- 긴급 수집: ingest_urgent_interval_minutes(기본 5분)마다 킥오프 임박(3시간 이내)
  경기의 오즈만 재수집.
- 정리: 매시 정각, 킥오프가 지난 경기의 combo_recommendations 캐시 삭제.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.clients.odds_api_client import OddsApiClient
from app.config import settings
from app.db import SessionLocal
from app.services.ingest import cleanup_past_combo_recommendations, run_ingest_cycle

logger = logging.getLogger("oddsapp.scheduler")

_scheduler: BackgroundScheduler | None = None


def _run_full_ingest_job() -> None:
    db = SessionLocal()
    try:
        summary = run_ingest_cycle(db, OddsApiClient(), urgent_only=False)
        logger.info("전체 수집 사이클 완료: %s", summary)
    except Exception:
        logger.exception("전체 수집 사이클 중 예외 발생")
    finally:
        db.close()


def _run_urgent_ingest_job() -> None:
    db = SessionLocal()
    try:
        summary = run_ingest_cycle(db, OddsApiClient(), urgent_only=True)
        logger.info("긴급 수집 사이클 완료: %s", summary)
    except Exception:
        logger.exception("긴급 수집 사이클 중 예외 발생")
    finally:
        db.close()


def _run_cleanup_job() -> None:
    db = SessionLocal()
    try:
        deleted = cleanup_past_combo_recommendations(db)
        logger.info("킥오프 지난 combo_recommendations %d건 정리", deleted)
    except Exception:
        logger.exception("정리 작업 중 예외 발생")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _run_full_ingest_job,
        "interval",
        minutes=settings.ingest_interval_minutes,
        id="full_ingest",
    )
    scheduler.add_job(
        _run_urgent_ingest_job,
        "interval",
        minutes=settings.ingest_urgent_interval_minutes,
        id="urgent_ingest",
    )
    scheduler.add_job(_run_cleanup_job, "interval", hours=1, id="cleanup_past_combos")
    scheduler.start()
    logger.info(
        "스케줄러 시작: 전체 수집 %d분, 긴급 수집 %d분 간격",
        settings.ingest_interval_minutes,
        settings.ingest_urgent_interval_minutes,
    )
    _scheduler = scheduler
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
