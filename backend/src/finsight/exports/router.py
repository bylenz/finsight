"""HTTP layer for the CSV export endpoint (FR-IO-01)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.deps import get_current_user
from finsight.auth.models import User
from finsight.db import get_session
from finsight.exports import service as export_service

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/csv")
async def export_expenses_csv(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    category_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    today = datetime.now(tz=UTC).date().isoformat()
    filename = f"finsight-expenses-{today}.csv"

    iterator = export_service.stream_expenses_csv(
        session,
        user,
        from_date=from_date,
        to_date=to_date,
        category_id=category_id,
    )

    return StreamingResponse(
        iterator,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
