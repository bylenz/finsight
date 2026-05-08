"""CRUD helpers for the LLM categorization cache.

Stays portable across SQLite (tests) and PostgreSQL (prod) by avoiding
dialect-specific ON CONFLICT — we pre-check, then insert.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.insights.models import CategoryCache


async def get_cached_category(session: AsyncSession, normalized: str) -> int | None:
    """Return the cached category id for a normalized description, if any."""
    return await session.scalar(
        select(CategoryCache.category_id).where(CategoryCache.normalized_description == normalized)
    )


async def set_cached_category(session: AsyncSession, normalized: str, category_id: int) -> None:
    """Idempotently store a (normalized_description -> category_id) mapping.

    If a row already exists for this key we leave it as-is (first writer wins),
    which is fine because the value is just a heuristic suggestion.
    """
    existing = await get_cached_category(session, normalized)
    if existing is not None:
        return
    session.add(CategoryCache(normalized_description=normalized, category_id=category_id))
    await session.flush()
