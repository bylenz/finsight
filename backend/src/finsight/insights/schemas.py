"""Pydantic schemas for the weekly AI insights endpoint (FR-IO-02)."""

from __future__ import annotations

from pydantic import BaseModel


class InsightResponse(BaseModel):
    """Weekly financial insight for the authenticated user.

    ``ai_generated`` is True when the LLM produced the text and False when a
    deterministic fallback was used (no API key, circuit breaker open, LLM
    failure, or empty spend month). The fallback is ALWAYS meaningful so the
    Insights tab never shows a hard error to the end user.
    """

    month: str
    currency: str
    ai_generated: bool
    summary: str
    highlights: list[str]
