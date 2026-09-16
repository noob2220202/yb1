from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ComboRecommendation(Base):
    __tablename__ = "combo_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False
    )
    leg_a_market_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("markets.id"), nullable=True
    )
    leg_a_selection: Mapped[str | None] = mapped_column(String(50), nullable=True)
    leg_b_market_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("markets.id"), nullable=True
    )
    leg_b_selection: Mapped[str | None] = mapped_column(String(50), nullable=True)
    combo_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    implied_hit_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    breakeven_prob: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    estimated_ev_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    stake_leg_a: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    stake_leg_b: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_stake: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    target_profit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
