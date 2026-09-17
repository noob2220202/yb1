from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Pick(Base):
    """저장된 픽(조합) — 경기 상세 카드 또는 계산기에서 저장, 텔레그램으로 전송,
    이후 실제 스코어로 채점해 적중률 통계에 반영한다."""

    __tablename__ = "picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("fixtures.id", ondelete="SET NULL"), nullable=True
    )

    home_team: Mapped[str] = mapped_column(String(200), nullable=False)
    away_team: Mapped[str] = mapped_column(String(200), nullable=False)

    combo_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    leg_a_selection: Mapped[str] = mapped_column(String(50), nullable=False)
    leg_b_selection: Mapped[str] = mapped_column(String(50), nullable=False)
    favorite_side: Mapped[str] = mapped_column(String(10), nullable=False)  # 'home' | 'away'

    odds_leg_a: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    odds_leg_b: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    stake_leg_a: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    stake_leg_b: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_stake: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    target_profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    implied_hit_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    breakeven_prob: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    estimated_ev_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    home_score_actual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score_actual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome_scenario: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actual_profit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    telegram_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
