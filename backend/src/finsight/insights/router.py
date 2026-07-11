"""HTTP endpoint for AI-generated weekly insights (FR-IO-02)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.deps import get_current_user
from finsight.auth.models import User
from finsight.db import get_session
from finsight.insights.generator import generate_insights
from finsight.insights.schemas import InsightResponse

router = APIRouter(prefix="/insights", tags=["insights"])

# Same strict YYYY-MM pattern as the dashboard endpoint.
_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get("", response_model=InsightResponse)
async def get_insights(
    month: str | None = Query(default=None, pattern=_MONTH_PATTERN),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> InsightResponse:
    if month is None:
        now = datetime.now(tz=UTC)
        year, month_int = now.year, now.month
    else:
        year_str, month_str = month.split("-", 1)
        year, month_int = int(year_str), int(month_str)

    return await generate_insights(session, user, year, month_int)
