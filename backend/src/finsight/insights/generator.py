"""LLM-backed weekly financial insights (FR-IO-02).

Public API: ``async def generate_insights(session, user, year, month) -> InsightResponse``

Design — mirrors the categorizer's fail-open philosophy:
    * Builds the monthly dashboard aggregate (reuses dashboard.service) so the
      LLM reasonates over the SAME numbers the user sees.
    * When the month is empty, returns a friendly empty-state insight without
      contacting the LLM.
    * When the LLM is unavailable (no key, disabled, circuit breaker open, or
      the call raises), falls back to a DETERMINISTIC insight derived from the
      dashboard data. The fallback is always meaningful — the Insights tab
      never shows a hard error.
    * When the LLM succeeds, its JSON is parsed into summary + highlights.

The Anthropic client is reused from ``finsight.insights.categorizer`` so both
LLM consumers share a single cached client honoring ``anthropic_base_url``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import User
from finsight.config import settings
from finsight.dashboard.schemas import DashboardResponse
from finsight.dashboard.service import build_dashboard
from finsight.insights import categorizer as _cat
from finsight.insights.schemas import InsightResponse

logger = logging.getLogger(__name__)

# Insight prose is longer than a single category id; allow enough room for a
# short paragraph plus a few bullet highlights, in Spanish.
_MAX_TOKENS = 512

_SYSTEM_PROMPT = (
    "You are FinSight, a friendly Spanish-language personal-finance coach for "
    "users in Latin America. Given a JSON summary of a user's spending for a "
    "month, write a concise, motivating analysis. Reply with ONLY a JSON "
    'object of the form {"summary": string, "highlights": [string, ...]}. '
    '"summary" is one or two short sentences (max ~60 words). "highlights" '
    "is a list of 2 to 4 short actionable observations or recommendations "
    "(each max ~15 words). No markdown, no code fences, just the JSON."
)


async def _ask_llm(user_message: str) -> str | None:
    """Single shot to the Anthropic Messages API. Returns raw text or None.

    Raises propagate so the caller can log and fall back.
    """
    # Imported through the module so tests monkeypatching categorizer._get_client
    # also affect this consumer (a `from` import would bind the original object).
    client = _cat._get_client()
    response = await client.messages.create(
        model=settings.llm_model,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text  # type: ignore[no-any-return]


def _build_prompt(dashboard: DashboardResponse) -> str:
    """Render the dashboard aggregate as a compact JSON string for the LLM."""
    payload: dict[str, Any] = {
        "month": dashboard.month,
        "currency": dashboard.currency,
        "total_spent": str(dashboard.total_spent),
        "expense_count": dashboard.expense_count,
        "by_category": [
            {
                "name": c.category_name,
                "amount": str(c.amount),
                "percentage": round(c.percentage, 4),
            }
            for c in dashboard.by_category
        ],
        "by_week": [
            {"week_start": str(w.week_start), "amount": str(w.amount)} for w in dashboard.by_week
        ],
        "budgets": [
            {
                "category": b.category_name,
                "limit": str(b.limit),
                "spent": str(b.spent),
                "used_percentage": round(b.percentage, 4),
            }
            for b in dashboard.budgets
        ],
    }
    return (
        "Here is the user's spending data for the month. "
        "Generate the insight JSON now.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _parse_insights(raw: str) -> tuple[str, list[str]] | None:
    """Parse the LLM JSON response into (summary, highlights).

    Tolerates surrounding whitespace and (best-effort) a stray code fence.
    Returns None when the response cannot be understood so the caller falls
    back to the deterministic insight.
    """
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        # Drop an optional language tag like "json" on the first line.
        text = text.split("\n", 1)[-1] if "\n" in text else text
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get("summary")
    highlights = data.get("highlights")
    if not isinstance(summary, str) or not summary.strip():
        return None
    if not isinstance(highlights, list):
        highlights = []
    clean_highlights = [str(h).strip() for h in highlights if isinstance(h, str) and str(h).strip()]
    return summary.strip(), clean_highlights


def _fallback_insights(dashboard: DashboardResponse) -> InsightResponse:
    """Deterministic, meaningful insight computed from the dashboard data.

    Used when the LLM is unavailable or returns garbage. Never raises.
    """
    cur = dashboard.currency
    total = dashboard.total_spent
    top = dashboard.by_category[0] if dashboard.by_category else None

    if top is not None:
        pct = round(top.percentage * 100)
        summary = (
            f"Gastaste {total} {cur} en {dashboard.expense_count} "
            f"transacciones este mes. Tu categoría principal fue "
            f"{top.category_name} con el {pct}% del gasto."
        )
    else:
        summary = f"Gastaste {total} {cur} en {dashboard.expense_count} " f"transacciones este mes."

    highlights: list[str] = []
    if top is not None:
        highlights.append(
            f"📊 {top.category_name} concentra el {round(top.percentage * 100)}% de tu gasto."
        )

    over_budget = [b for b in dashboard.budgets if b.percentage >= 1.0]
    for b in over_budget:
        label = b.category_name or "presupuesto general"
        highlights.append(
            f"⚠️ Superaste tu presupuesto de {label} ({round(b.percentage * 100)}% usado)."
        )

    near_limit = [b for b in dashboard.budgets if 0.8 <= b.percentage < 1.0]
    for b in near_limit[:1]:
        label = b.category_name or "presupuesto general"
        highlights.append(
            f"🔵 Estás cerca del límite en {label} ({round(b.percentage * 100)}% usado)."
        )

    if dashboard.by_week:
        max_week = max(dashboard.by_week, key=lambda w: w.amount)
        if max_week.amount > 0:
            highlights.append(
                f"📈 La semana del {max_week.week_start} fue la de mayor gasto ({max_week.amount} {cur})."
            )

    return InsightResponse(
        month=dashboard.month,
        currency=dashboard.currency,
        ai_generated=False,
        summary=summary,
        highlights=highlights,
    )


def _from_llm(dashboard: DashboardResponse, summary: str, highlights: list[str]) -> InsightResponse:
    return InsightResponse(
        month=dashboard.month,
        currency=dashboard.currency,
        ai_generated=True,
        summary=summary,
        highlights=highlights,
    )


async def generate_insights(
    session: AsyncSession,
    user: User,
    year: int,
    month: int,
) -> InsightResponse:
    """Build a weekly/monthly insight for ``user`` over the given month.

    Order:
      1. Build the dashboard aggregate (single source of truth for the numbers).
      2. Empty month → friendly empty-state insight, no LLM call.
      3. No API key / disabled / circuit breaker open → deterministic fallback.
      4. Call the LLM; parse JSON; on success return the AI insight.
      5. On any failure or unparseable response → deterministic fallback.
    """
    dashboard = await build_dashboard(session, user, year, month, include_budgets=True)

    if dashboard.expense_count == 0:
        return InsightResponse(
            month=dashboard.month,
            currency=dashboard.currency,
            ai_generated=False,
            summary=(
                "Aún no tienes gastos registrados este mes. "
                "Empieza a registrar tus gastos para recibir análisis "
                "personalizados generados por IA."
            ),
            highlights=[],
        )

    if not _cat._api_key():
        logger.info("No anthropic_api_key configured — using deterministic insights fallback")
        return _fallback_insights(dashboard)

    if not settings.llm_categorizer_enabled:
        logger.debug("LLM disabled (llm_categorizer_enabled=False) — using deterministic fallback")
        return _fallback_insights(dashboard)

    if _cat._circuit_breaker_is_open():
        logger.warning(
            "LLM circuit breaker is OPEN — using deterministic insights fallback",
        )
        return _fallback_insights(dashboard)

    try:
        raw = await _ask_llm(_build_prompt(dashboard))
    except Exception as exc:
        logger.warning("LLM insights generation failed (%s) — using deterministic fallback", exc)
        return _fallback_insights(dashboard)

    if raw is None:
        return _fallback_insights(dashboard)

    parsed = _parse_insights(raw)
    if parsed is None:
        logger.warning("LLM returned unparseable insights %r — using deterministic fallback", raw)
        return _fallback_insights(dashboard)

    summary, highlights = parsed
    return _from_llm(dashboard, summary, highlights)
