"""Budgets service — CRUD + status calculation.

All operations are scoped to the caller's household. A budget with
``category_id IS NULL`` is treated as the household's overall monthly cap.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import User
from finsight.budgets.models import Budget
from finsight.budgets.schemas import BudgetCreate, BudgetUpdate
from finsight.expenses.models import Expense
from finsight.households.models import Household, HouseholdMember, HouseholdRole


class BudgetNotFoundError(Exception):
    pass


class BudgetForbiddenError(Exception):
    pass


async def _ensure_personal_household(session: AsyncSession, user: User) -> Household:
    """Mirror of expenses.service._ensure_personal_household.

    Lazily creates a "Personal" household for the user if none exists.
    """
    existing = await session.scalar(select(Household).where(Household.owner_id == user.id).limit(1))
    if existing is not None:
        return existing
    hh = Household(name="Personal", owner_id=user.id)
    session.add(hh)
    await session.flush()
    session.add(
        HouseholdMember(household_id=hh.id, user_id=user.id, role=HouseholdRole.OWNER.value)
    )
    await session.flush()
    return hh


async def _resolve_user_household(session: AsyncSession, user: User) -> Household:
    return await _ensure_personal_household(session, user)


def _month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return [start_of_month, start_of_next_month) in UTC."""
    now = now or datetime.now(tz=UTC)
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    return start, end


async def create_budget(session: AsyncSession, user: User, payload: BudgetCreate) -> Budget:
    household = await _resolve_user_household(session, user)
    budget = Budget(
        household_id=household.id,
        category_id=payload.category_id,
        amount=payload.amount,
        currency=payload.currency,
        period=payload.period,
    )
    session.add(budget)
    await session.commit()
    await session.refresh(budget)
    return budget


async def list_budgets(
    session: AsyncSession,
    user: User,
    *,
    category_id: int | None = None,
) -> list[Budget]:
    household = await _resolve_user_household(session, user)
    stmt = select(Budget).where(Budget.household_id == household.id)
    if category_id is not None:
        stmt = stmt.where(Budget.category_id == category_id)
    stmt = stmt.order_by(Budget.id.asc())
    return list((await session.execute(stmt)).scalars().all())


async def _get_owned_budget(session: AsyncSession, user: User, budget_id: int) -> Budget:
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise BudgetNotFoundError(budget_id)
    household = await _resolve_user_household(session, user)
    if budget.household_id != household.id:
        raise BudgetForbiddenError(budget_id)
    return budget


async def get_budget(session: AsyncSession, user: User, budget_id: int) -> Budget:
    return await _get_owned_budget(session, user, budget_id)


async def update_budget(
    session: AsyncSession, user: User, budget_id: int, payload: BudgetUpdate
) -> Budget:
    budget = await _get_owned_budget(session, user, budget_id)
    budget.amount = payload.amount
    budget.currency = payload.currency
    budget.period = payload.period
    budget.category_id = payload.category_id
    await session.commit()
    await session.refresh(budget)
    return budget


async def delete_budget(session: AsyncSession, user: User, budget_id: int) -> None:
    budget = await _get_owned_budget(session, user, budget_id)
    await session.delete(budget)
    await session.commit()


async def compute_budget_spend(
    session: AsyncSession, budget: Budget, *, now: datetime | None = None
) -> Decimal:
    """Sum current-month expense amounts within the budget's scope."""
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


async def get_budget_status(
    session: AsyncSession, user: User, budget_id: int
) -> tuple[Decimal, Decimal, float, str]:
    budget = await _get_owned_budget(session, user, budget_id)
    spent = await compute_budget_spend(session, budget)
    limit = Decimal(budget.amount)
    percentage = float(spent / limit) if limit > 0 else 0.0
    return spent, limit, percentage, budget.currency
