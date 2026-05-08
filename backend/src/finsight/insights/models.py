from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from finsight.db import Base


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class CategoryCache(Base):
    """LLM categorization cache.

    Maps a normalized expense description to a previously chosen category id.
    Look-ups are case- and whitespace-insensitive (see categorizer._normalize).
    Skipping the LLM on a hit keeps the categorize() path well under NFR-02
    (< 2s p95).
    """

    __tablename__ = "category_cache"

    normalized_description: Mapped[str] = mapped_column(String(255), primary_key=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
