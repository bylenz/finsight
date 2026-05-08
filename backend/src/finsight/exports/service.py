"""Streaming CSV export service for expenses (FR-IO-01)."""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import User
from finsight.categories.models import Category
from finsight.expenses.models import Expense

CSV_HEADER: tuple[str, ...] = (
    "id",
    "occurred_at",
    "description",
    "category",
    "amount",
    "currency",
    "amount_base",
    "is_business",
    "source",
)


def _format_csv_row(values: list[str]) -> str:
    """Encode a single row using csv.writer to ensure RFC 4180 compliance."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(values)
    return buf.getvalue()


def _format_occurred_at(value: datetime) -> str:
    """Return ISO 8601 UTC representation of an occurred_at timestamp.

    SQLite drops timezone info, so naive datetimes are assumed UTC for output
    consistency.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


async def stream_expenses_csv(
    session: AsyncSession,
    user: User,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    category_id: int | None = None,
) -> AsyncIterator[str]:
    """Yield CSV lines for the caller's expenses, one row at a time.

    Joining `categories` lets us project the category name in a single query
    without a separate lookup per row.
    """
    yield _format_csv_row(list(CSV_HEADER))

    stmt = (
        select(Expense, Category.name)
        .join(Category, Category.id == Expense.category_id, isouter=True)
        .where(Expense.user_id == user.id)
    )
    if from_date is not None:
        from_dt = datetime.combine(from_date, datetime.min.time(), tzinfo=UTC)
        stmt = stmt.where(Expense.occurred_at >= from_dt)
    if to_date is not None:
        to_dt = datetime.combine(to_date, datetime.max.time(), tzinfo=UTC)
        stmt = stmt.where(Expense.occurred_at <= to_dt)
    if category_id is not None:
        stmt = stmt.where(Expense.category_id == category_id)
    stmt = stmt.order_by(Expense.occurred_at.desc(), Expense.id.desc())

    result = await session.stream(stmt)
    async for expense, category_name in result:
        row = [
            str(expense.id),
            _format_occurred_at(expense.occurred_at),
            expense.description or "",
            category_name or "",
            f"{expense.amount:.2f}",
            expense.currency,
            f"{expense.amount_base:.2f}",
            "true" if expense.is_business else "false",
            expense.source,
        ]
        yield _format_csv_row(row)
