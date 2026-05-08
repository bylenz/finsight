"""LLM-backed expense auto-categorization (FR-EXP-02).

Public API: ``async def categorize(description, available_categories, session) -> int``

Guarantees:
    * Always returns a valid Category.id from ``available_categories`` (or the
      global "Other" fallback). NEVER raises — even when the Anthropic SDK is
      unreachable, the API key is missing, or the model returns garbage.
    * Skips the LLM entirely when a cache row exists for the normalized
      description, keeping warm-path latency well under NFR-02 (< 2s p95).
    * Manual overrides (caller passing an explicit ``category_id`` upstream)
      bypass this module entirely — see expenses.service.create_expense.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.categories.models import Category
from finsight.categories.service import seed_default_categories
from finsight.config import settings
from finsight.insights import cache_service

logger = logging.getLogger(__name__)

# Cheap, fast model — comfortably inside NFR-02 (< 2s p95).
_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 16  # we only need an integer back

_SYSTEM_PROMPT = (
    "You are a Spanish-language expense categorizer for personal finance in "
    "Latin America. The user will give you an expense description and a JSON "
    "list of candidate categories with their numeric IDs. Choose the SINGLE "
    "best-matching category. Reply with ONLY the integer ID of that category "
    "— no words, no punctuation, no explanation, just the number."
)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(description: str) -> str:
    """Lowercase, strip, and collapse internal whitespace."""
    return _WHITESPACE_RE.sub(" ", description.strip().lower())


def _api_key() -> str:
    """Indirection so tests can monkeypatch the key without touching settings."""
    return settings.anthropic_api_key


@lru_cache(maxsize=1)
def _get_client():  # type: ignore[no-untyped-def]
    """Lazily build a single AsyncAnthropic client.

    Imported lazily so the SDK is never touched in environments without a key
    (and so tests can monkeypatch this function before the SDK is imported).
    """
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=_api_key())


def _build_user_message(description: str, categories: list[Category]) -> str:
    serialized = ", ".join(f'{{"id": {c.id}, "name": "{c.name}"}}' for c in categories)
    return (
        f'Expense description: "{description}"\n'
        f"Candidate categories: [{serialized}]\n\n"
        "Reply with the integer ID only."
    )


async def _other_category_id(
    session: AsyncSession, available_categories: list[Category]
) -> int:
    """Find the global "Other" category, preferring the in-memory list."""
    for c in available_categories:
        if c.household_id is None and c.name == "Other":
            return c.id
    cat_id = await session.scalar(
        select(Category.id).where(Category.household_id.is_(None), Category.name == "Other")
    )
    if cat_id is not None:
        return cat_id
    await seed_default_categories(session)
    cat_id = await session.scalar(
        select(Category.id).where(Category.household_id.is_(None), Category.name == "Other")
    )
    assert cat_id is not None  # seed guarantees presence
    return cat_id


async def _ask_llm(description: str, categories: list[Category]) -> str | None:
    """Single shot to the Anthropic Messages API. Returns the raw text or None."""
    try:
        client = _get_client()
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(description, categories)}],
        )
        # response.content is a list of content blocks; the first is text.
        return response.content[0].text  # type: ignore[no-any-return]
    except Exception as exc:  # noqa: BLE001 — categorizer NEVER raises
        logger.warning("LLM categorization failed (%s) — using Other fallback", exc)
        return None


def _parse_category_id(text: str, categories: list[Category]) -> int | None:
    """Return an int id if it parses cleanly AND belongs to ``categories``."""
    try:
        cid = int(text.strip())
    except (ValueError, AttributeError):
        return None
    if not any(c.id == cid for c in categories):
        return None
    return cid


async def categorize(
    description: str | None,
    available_categories: list[Category],
    session: AsyncSession,
) -> int:
    """Pick the best category id for ``description``.

    Order:
      1. Cache hit on normalized description -> return cached id.
      2. No API key -> fall back to "Other".
      3. Call Anthropic; parse integer id; validate against available set.
      4. On any failure -> fall back to "Other".

    On a successful LLM hit, the result is written to the cache.
    """
    if not description or not description.strip():
        return await _other_category_id(session, available_categories)

    normalized = _normalize(description)

    cached = await cache_service.get_cached_category(session, normalized)
    if cached is not None:
        return cached

    if not _api_key():
        logger.info("No anthropic_api_key configured — using Other fallback")
        return await _other_category_id(session, available_categories)

    raw = await _ask_llm(description, available_categories)
    if raw is None:
        return await _other_category_id(session, available_categories)

    chosen = _parse_category_id(raw, available_categories)
    if chosen is None:
        logger.warning("LLM returned unusable category id %r — using Other fallback", raw)
        return await _other_category_id(session, available_categories)

    await cache_service.set_cached_category(session, normalized, chosen)
    return chosen


async def load_available_categories(
    session: AsyncSession, household_id: int | None
) -> list[Category]:
    """Return global ∪ this-household categories — never any other household's."""
    stmt = select(Category).where(
        (Category.household_id.is_(None)) | (Category.household_id == household_id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
