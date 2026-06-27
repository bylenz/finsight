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

# Model id is read from settings so the same code talks to Anthropic Claude or
# any Anthropic-protocol-compatible provider (e.g. Z.ai GLM at glm-4.5-air).
# Default in config.py targets Claude Haiku — comfortably inside NFR-02 (< 2s p95).
_MAX_TOKENS = 16  # we only need an integer back

# ---------------------------------------------------------------------------
# Circuit breaker — in-process, fail-open
# ---------------------------------------------------------------------------
# Tracks consecutive LLM call failures.  When the count reaches
# settings.llm_circuit_breaker_threshold, the breaker OPENS and subsequent
# calls return the "Other" fallback without contacting the Anthropic API.
# The breaker resets to CLOSED on the first successful LLM call.
# This state is module-level so it persists across requests in the same
# worker process.  It does NOT persist across process restarts (by design —
# transient outages self-heal on next deploy/restart).
_circuit_breaker_consecutive_failures: int = 0


def _circuit_breaker_is_open() -> bool:
    return _circuit_breaker_consecutive_failures >= settings.llm_circuit_breaker_threshold


def _circuit_breaker_record_failure() -> None:
    global _circuit_breaker_consecutive_failures
    _circuit_breaker_consecutive_failures += 1
    if _circuit_breaker_is_open():
        logger.warning(
            "LLM circuit breaker OPENED after %d consecutive failures — "
            "all subsequent calls will use the 'Other' fallback until a "
            "successful response is received.",
            _circuit_breaker_consecutive_failures,
        )


def _circuit_breaker_record_success() -> None:
    global _circuit_breaker_consecutive_failures
    if _circuit_breaker_consecutive_failures > 0:
        logger.info("LLM circuit breaker CLOSED after successful response.")
    _circuit_breaker_consecutive_failures = 0


def reset_circuit_breaker() -> None:
    """Reset circuit breaker state.  Intended for tests only."""
    global _circuit_breaker_consecutive_failures
    _circuit_breaker_consecutive_failures = 0


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

    Honors ``settings.anthropic_base_url`` so the same client can talk to a
    drop-in Anthropic-compatible provider (e.g. Z.ai GLM at
    https://api.z.ai/api/anthropic).
    """
    from anthropic import AsyncAnthropic

    kwargs: dict[str, str] = {"api_key": _api_key()}
    if settings.anthropic_base_url:
        kwargs["base_url"] = settings.anthropic_base_url
    return AsyncAnthropic(**kwargs)


def _build_user_message(description: str, categories: list[Category]) -> str:
    serialized = ", ".join(f'{{"id": {c.id}, "name": "{c.name}"}}' for c in categories)
    return (
        f'Expense description: "{description}"\n'
        f"Candidate categories: [{serialized}]\n\n"
        "Reply with the integer ID only."
    )


async def _other_category_id(session: AsyncSession, available_categories: list[Category]) -> int:
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
    """Single shot to the Anthropic Messages API. Returns the raw text or None.

    Exceptions are allowed to propagate so the circuit breaker in ``categorize``
    can count consecutive failures.
    """
    client = _get_client()
    response = await client.messages.create(
        model=settings.llm_model,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(description, categories)}],
    )
    # response.content is a list of content blocks; the first is text.
    return response.content[0].text  # type: ignore[no-any-return]


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

    # Guard 1: opt-in flag — when disabled, skip LLM entirely (fail-open).
    if not settings.llm_categorizer_enabled:
        logger.debug(
            "LLM categorizer disabled (llm_categorizer_enabled=False) — using Other fallback"
        )
        return await _other_category_id(session, available_categories)

    # Guard 2: circuit breaker — OPEN means too many consecutive failures; skip LLM.
    if _circuit_breaker_is_open():
        logger.warning(
            "LLM circuit breaker is OPEN (%d failures) — using Other fallback without LLM call",
            _circuit_breaker_consecutive_failures,
        )
        return await _other_category_id(session, available_categories)

    # Call LLM with circuit breaker tracking.
    try:
        raw = await _ask_llm(description, available_categories)
    except Exception as exc:
        _circuit_breaker_record_failure()
        logger.warning("LLM categorization failed (%s) — using Other fallback", exc)
        return await _other_category_id(session, available_categories)

    # Successful SDK call — reset failure counter.
    _circuit_breaker_record_success()

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
    """Return global + this-household categories — never any other household's."""
    stmt = select(Category).where(
        (Category.household_id.is_(None)) | (Category.household_id == household_id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
