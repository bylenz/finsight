"""Budget alert evaluation — emits idempotent 80% and 100% threshold alerts.

Invoked from ``expenses.service.create_expense`` after an expense lands.
The expense create path MUST treat any failure here as non-fatal and log a
warning instead of propagating.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import User
from finsight.budgets.models import Alert, AlertType, Budget
from finsight.budgets.service import _month_bounds
from finsight.expenses.models import Expense
from finsight.households.models import Household

logger = logging.getLogger(__name__)


async def _spend_for_budget(
    session: AsyncSession, budget: Budget, *, now: datetime | None = None
) -> Decimal:
    start, end = _month_bounds(now)
    stmt = (
        select(func.coalesce(func.sum(Expense.amount), 0))
        .where(Expense.household_id == budget.household_id)
        .where(Expense.occurred_at >= start)
        .where(Expense.occurred_at < end)
    )
    if budget.category_id is not None:
        stmt = stmt.where(Expense.category_id == budget.category_id)
    total = await session.scalar(stmt)
    return Decimal(total or 0)


async def _alert_exists(
    session: AsyncSession, budget_id: int, alert_type: str, now: datetime
) -> bool:
    start, end = _month_bounds(now)
    stmt = (
        select(Alert.id)
        .where(Alert.budget_id == budget_id)
        .where(Alert.type == alert_type)
        .where(Alert.triggered_at >= start)
        .where(Alert.triggered_at < end)
        .limit(1)
    )
    return (await session.scalar(stmt)) is not None


async def evaluate_alerts_for_user(session: AsyncSession, user: User) -> list[Alert]:
    """Evaluate every budget owned by the user's household and emit alerts.

    Idempotent — if an alert of the same type already exists for the budget
    in the current month, it is not re-inserted.
    """
    household = await session.scalar(
        select(Household).where(Household.owner_id == user.id).limit(1)
    )
    if household is None:
        return []

    budgets = list(
        (await session.execute(select(Budget).where(Budget.household_id == household.id))).scalars()
    )
    if not budgets:
        return []

    now = datetime.now(tz=UTC)
    created: list[Alert] = []

    for budget in budgets:
        limit = Decimal(budget.amount)
        if limit <= 0:
            continue
        spent = await _spend_for_budget(session, budget, now=now)
        ratio = spent / limit

        # Always evaluate 80% first then 100% so both can fire on the same expense.
        if ratio >= Decimal("0.8") and not await _alert_exists(
            session, budget.id, AlertType.WARN_80.value, now
        ):
            alert = Alert(
                user_id=user.id,
                budget_id=budget.id,
                type=AlertType.WARN_80.value,
                triggered_at=now,
            )
            session.add(alert)
            await session.flush()
            created.append(alert)

        if ratio >= Decimal("1.0") and not await _alert_exists(
            session, budget.id, AlertType.OVER_100.value, now
        ):
            alert = Alert(
                user_id=user.id,
                budget_id=budget.id,
                type=AlertType.OVER_100.value,
                triggered_at=now,
            )
            session.add(alert)
            await session.flush()
            created.append(alert)

    if created:
        await session.commit()
    return created


async def list_alerts_for_user(session: AsyncSession, user: User) -> list[Alert]:
    stmt = (
        select(Alert)
        .where(Alert.user_id == user.id)
        .order_by(Alert.triggered_at.desc(), Alert.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
