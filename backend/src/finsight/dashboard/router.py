"""HTTP endpoint for the monthly dashboard aggregate (FR-DASH-01..03)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.deps import get_current_user
from finsight.auth.models import User
from finsight.dashboard.schemas import DashboardResponse
from finsight.dashboard.service import build_dashboard
from finsight.db import get_session

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Strict YYYY-MM (months 01..12). Bad input → FastAPI returns 422.
_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    month: str | None = Query(default=None, pattern=_MONTH_PATTERN),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DashboardResponse:
    if month is None:
        now = datetime.now(tz=UTC)
        year, month_int = now.year, now.month
    else:
        year_str, month_str = month.split("-", 1)
        year, month_int = int(year_str), int(month_str)

    return await build_dashboard(session, user, year, month_int)
