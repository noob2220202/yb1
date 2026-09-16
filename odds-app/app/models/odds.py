from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Odds(Base):
    __tablename__ = "odds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("markets.id", ondelete="CASCADE"), nullable=False
    )
    selection: Mapped[str] = mapped_column(String(50), nullable=False)
    decimal_odds: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    market: Mapped["Market"] = relationship("Market", back_populates="odds")
