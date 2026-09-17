"""픽 저장/채점 오케스트레이션 — 경기 상세 카드와 계산기, 두 진입점이 공유한다.

저장 시 텔레그램으로 바로 전송한다(.env에 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID가
없으면 조용히 스킵). 채점 시에도 결과를 텔레그램으로 후속 전송한다.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.pick import Pick
from app.services.grading import grade_pick
from app.services.staking import compute_quality_grade
from app.services.telegram_client import format_pick_message, format_result_message, send_telegram_message


def save_pick(
    db: Session,
    *,
    fixture_id: int | None,
    home_team: str,
    away_team: str,
    combo_type: str,
    description: str,
    leg_a_selection: str,
    leg_b_selection: str,
    favorite_side: str,
    odds_leg_a: float,
    odds_leg_b: float,
    stake_leg_a: float,
    stake_leg_b: float,
    total_stake: float,
    target_profit: float,
    implied_hit_rate: float | None = None,
    breakeven_prob: float | None = None,
    estimated_ev_pct: float | None = None,
) -> Pick:
    pick = Pick(
        fixture_id=fixture_id,
        home_team=home_team,
        away_team=away_team,
        combo_type=combo_type,
        description=description,
        leg_a_selection=leg_a_selection,
        leg_b_selection=leg_b_selection,
        favorite_side=favorite_side,
        odds_leg_a=odds_leg_a,
        odds_leg_b=odds_leg_b,
        stake_leg_a=stake_leg_a,
        stake_leg_b=stake_leg_b,
        total_stake=total_stake,
        target_profit=target_profit,
        implied_hit_rate=implied_hit_rate,
        breakeven_prob=breakeven_prob,
        estimated_ev_pct=estimated_ev_pct,
        quality_grade=compute_quality_grade(estimated_ev_pct, implied_hit_rate, breakeven_prob),
        status="pending",
    )
    db.add(pick)
    db.commit()
    db.refresh(pick)

    sent = send_telegram_message(format_pick_message(pick))
    if sent:
        pick.telegram_sent = True
        db.commit()

    return pick


def grade_and_notify(db: Session, pick: Pick, home_score: int, away_score: int) -> Pick:
    result = grade_pick(pick, home_score, away_score)

    pick.home_score_actual = home_score
    pick.away_score_actual = away_score
    pick.outcome_scenario = result["scenario"]
    pick.actual_profit = result["net_profit"]
    pick.hit = result["net_profit"] > 0
    pick.status = "settled"
    pick.settled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pick)

    send_telegram_message(format_result_message(pick))
    return pick


def compute_stats(db: Session) -> dict:
    """적중률/손익 통계 — 채점 완료(settled)된 픽만 집계 대상."""
    settled = db.query(Pick).filter(Pick.status == "settled").all()
    pending_count = db.query(Pick).filter(Pick.status == "pending").count()

    total = len(settled)
    hits = sum(1 for p in settled if p.hit)
    total_profit = sum(float(p.actual_profit) for p in settled if p.actual_profit is not None)
    total_staked = sum(float(p.total_stake) for p in settled)

    by_combo_type: dict[str, dict] = {}
    for p in settled:
        bucket = by_combo_type.setdefault(
            p.combo_type, {"count": 0, "hits": 0, "profit": 0.0, "staked": 0.0}
        )
        bucket["count"] += 1
        bucket["hits"] += 1 if p.hit else 0
        bucket["profit"] += float(p.actual_profit) if p.actual_profit is not None else 0.0
        bucket["staked"] += float(p.total_stake)

    for bucket in by_combo_type.values():
        bucket["hit_rate"] = bucket["hits"] / bucket["count"] if bucket["count"] else None
        bucket["roi_pct"] = (bucket["profit"] / bucket["staked"] * 100) if bucket["staked"] else None

    return {
        "settled_count": total,
        "pending_count": pending_count,
        "hits": hits,
        "hit_rate": (hits / total) if total else None,
        "total_profit": total_profit,
        "total_staked": total_staked,
        "roi_pct": (total_profit / total_staked * 100) if total_staked else None,
        "by_combo_type": by_combo_type,
    }
