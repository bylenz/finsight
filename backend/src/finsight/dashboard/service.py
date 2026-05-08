"""Dashboard aggregation service (FR-DASH-01..03).

Builds a monthly summary scoped to the authenticated user:
- total spent + expense count
- breakdown by category (only categories with non-zero spend, sorted desc)
- breakdown by ISO week (Monday-anchored), bounded to the target month
- household budgets with current-month spend (when month == current month)

Performance contract (NFR-01): two grouped SQL queries — no per-category
N+1 fan-out. Week bucketing is done in Python after a single SELECT to
keep the SQL portable across SQLite and PostgreSQL (their week-of-year
semantics differ — SQLite ``strftime('%W', ...)`` is Sunday-anchored,
Postgres ``date_trunc('week', ...)`` is Monday-anchored ISO).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import User
from finsight.budgets import service as budget_service
from finsight.budgets.models import Budget
from finsight.categories.models import Category
from finsight.config import settings
from finsight.dashboard.schemas import (
    BudgetSummary,
    CategoryBreakdown,
    DashboardResponse,
    WeekBreakdown,
)
from finsight.expenses.models import Expense


def _month_window(year: int, month: int) -> tuple[datetime, datetime]:
    """Return ``[start_of_month, start_of_next_month)`` in UTC."""
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC)
    return start, end


def _ensure_aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes — assume UTC for ISO-week bucketing."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _iso_week_start(d: date) -> date:
    """Monday of the ISO week containing ``d``."""
    return d - timedelta(days=d.weekday())


def _build_week_buckets(
    rows: list[tuple[datetime, Decimal]],
    month_start: datetime,
    month_end: datetime,
) -> list[WeekBreakdown]:
    """Bucket expenses into Monday-anchored ISO weeks intersecting the month.

    Every ISO week that touches [month_start, month_end) appears as a
    bucket — including weeks straddling adjacent months — but expenses
    falling outside the target month are NOT counted toward any bucket.
    """
    buckets: dict[date, Decimal] = {}

    # Seed buckets for every ISO week intersecting the month so we always
    # return the structural skeleton even when there is zero spend.
    cursor = _iso_week_start(month_start.date())
    last_day = (month_end - timedelta(days=1)).date()
    while cursor <= last_day:
        buckets[cursor] = Decimal("0")
        cursor += timedelta(days=7)

    for occurred_at, amount_base in rows:
        occurred = _ensure_aware(occurred_at)
        # Already filtered by SQL to within [month_start, month_end), so
        # this is just a defensive guard.
        if occurred < month_start or occurred >= month_end:
            continue
        wk = _iso_week_start(occurred.date())
        buckets[wk] = buckets.get(wk, Decimal("0")) + Decimal(amount_base)

    return [
        WeekBreakdown(week_start=ws, week_end=ws + timedelta(days=6), amount=amount)
        for ws, amount in sorted(buckets.items())
    ]


async def _by_category(
    session: AsyncSession,
    user: User,
    month_start: datetime,
    month_end: datetime,
) -> tuple[list[CategoryBreakdown], Decimal, int]:
    """Single grouped SELECT: per-category sum + count, joined to category names."""
    stmt = (
        select(
            Expense.category_id,
            Category.name,
            func.coalesce(func.sum(Expense.amount_base), 0).label("amount"),
            func.count(Expense.id).label("count"),
        )
        .join(Category, Category.id == Expense.category_id, isouter=True)
        .where(Expense.user_id == user.id)
        .where(Expense.occurred_at >= month_start)
        .where(Expense.occurred_at < month_end)
        .where(Expense.category_id.is_not(None))
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount_base).desc())
    )
    rows = (await session.execute(stmt)).all()

    total = Decimal("0")
    count = 0
    breakdowns: list[tuple[int, str, Decimal]] = []
    for category_id, category_name, amount, cnt in rows:
        amount_dec = Decimal(amount or 0)
        total += amount_dec
        count += int(cnt)
        # Only categories with non-zero spend appear (handled by GROUP BY +
        # the implicit filter that rows only exist when there are expenses).
        if amount_dec > 0:
            breakdowns.append((int(category_id), category_name or "", amount_dec))

    items = [
        CategoryBreakdown(
            category_id=cid,
            category_name=cname,
            amount=amount,
            percentage=float(amount / total) if total > 0 else 0.0,
        )
        for cid, cname, amount in breakdowns
    ]
    return items, total, count


async def _by_week(
    session: AsyncSession,
    user: User,
    month_start: datetime,
    month_end: datetime,
) -> list[WeekBreakdown]:
    stmt = (
        select(Expense.occurred_at, Expense.amount_base)
        .where(Expense.user_id == user.id)
        .where(Expense.occurred_at >= month_start)
        .where(Expense.occurred_at < month_end)
    )
    rows = (await session.execute(stmt)).all()
    return _build_week_buckets([(r[0], Decimal(r[1])) for r in rows], month_start, month_end)


async def _budgets_summary(
    session: AsyncSession,
    user: User,
    *,
    now: datetime,
) -> list[BudgetSummary]:
    """Reuse ``budgets.service.compute_budget_spend`` (no duplication).

    Returns every budget in the user's household with current-month spend.
    """
    household = await budget_service._resolve_user_household(session, user)
    stmt = (
        select(Budget, Category.name)
        .join(Category, Category.id == Budget.category_id, isouter=True)
        .where(Budget.household_id == household.id)
        .order_by(Budget.id.asc())
    )
    rows = (await session.execute(stmt)).all()

    summaries: list[BudgetSummary] = []
    for budget, category_name in rows:
        spent = await budget_service.compute_budget_spend(session, budget, now=now)
        limit = Decimal(budget.amount)
        percentage = float(spent / limit) if limit > 0 else 0.0
        summaries.append(
            BudgetSummary(
                budget_id=budget.id,
                category_id=budget.category_id,
                category_name=category_name,
                limit=limit,
                spent=spent,
                percentage=percentage,
            )
        )
    return summaries


async def build_dashboard(
    session: AsyncSession,
    user: User,
    year: int,
    month: int,
    *,
    include_budgets: bool = True,
) -> DashboardResponse:
    month_start, month_end = _month_window(year, month)

    by_category, total_spent, expense_count = await _by_category(
        session, user, month_start, month_end
    )
    by_week = await _by_week(session, user, month_start, month_end)

    budgets: list[BudgetSummary] = []
    if include_budgets:
        # Budget spend is always evaluated against the *current* month (the
        # only `period` we support). Anchor `now` inside the requested month
        # so that historical dashboards still reflect that month's spend.
        anchor = month_start + timedelta(days=1)
        budgets = await _budgets_summary(session, user, now=anchor)

    return DashboardResponse(
        month=f"{year:04d}-{month:02d}",
        currency=settings.base_currency,
        total_spent=total_spent,
        expense_count=expense_count,
        by_category=by_category,
        by_week=by_week,
        budgets=budgets,
    )
