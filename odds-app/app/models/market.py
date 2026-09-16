from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False
    )
    market_type: Mapped[str] = mapped_column(String(50), nullable=False)
    line: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    bookmaker: Mapped[str] = mapped_column(String(50), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    fixture: Mapped["Fixture"] = relationship("Fixture", back_populates="markets")
    odds: Mapped[list["Odds"]] = relationship(
        "Odds", back_populates="market", cascade="all, delete-orphan"
    )
