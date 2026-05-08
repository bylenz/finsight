import logging
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import User
from finsight.budgets import alerts as budget_alerts
from finsight.categories.service import seed_default_categories
from finsight.expenses.models import Expense
from finsight.expenses.schemas import ExpenseCreate, ExpenseUpdate
from finsight.households.models import Household, HouseholdMember, HouseholdRole
from finsight.insights import categorizer

logger = logging.getLogger(__name__)


class ExpenseNotFoundError(Exception):
    pass


class ExpenseForbiddenError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


async def _ensure_personal_household(session: AsyncSession, user: User) -> Household:
    """Return user's personal household, creating one if none exists.

    Households are not yet exposed via API; for solo expense tracking we lazily
    create a "Personal" household per user on their first expense.
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


async def create_expense(session: AsyncSession, user: User, payload: ExpenseCreate) -> Expense:
    household = await _ensure_personal_household(session, user)
    category_id = payload.category_id
    if category_id is None:
        # Ensure defaults exist so the categorizer (and its Other fallback)
        # always has something to choose from.
        await seed_default_categories(session)
        available = await categorizer.load_available_categories(session, household.id)
        category_id = await categorizer.categorize(payload.description, available, session)

    # amount_base mirrors amount until multi-currency conversion lands.
    amount_base: Decimal = payload.amount

    expense = Expense(
        user_id=user.id,
        household_id=household.id,
        amount=payload.amount,
        currency=payload.currency,
        amount_base=amount_base,
        category_id=category_id,
        description=payload.description,
        occurred_at=payload.occurred_at or _utcnow(),
        is_business=payload.is_business,
        source=payload.source or "manual",
    )
    session.add(expense)
    await session.commit()
    await session.refresh(expense)

    # Alert evaluation must never block expense creation.
    try:
        await budget_alerts.evaluate_alerts_for_user(session, user)
    except Exception as exc:
        logger.warning("Budget alert evaluation failed for user %s: %s", user.id, exc)

    return expense


async def list_expenses(
    session: AsyncSession,
    user: User,
    *,
    limit: int,
    offset: int,
    from_date: date | None = None,
    to_date: date | None = None,
    category_id: int | None = None,
) -> tuple[list[Expense], int]:
    stmt = select(Expense).where(Expense.user_id == user.id)
    count_stmt = select(func.count()).select_from(Expense).where(Expense.user_id == user.id)

    if from_date is not None:
        from_dt = datetime.combine(from_date, datetime.min.time(), tzinfo=UTC)
        stmt = stmt.where(Expense.occurred_at >= from_dt)
        count_stmt = count_stmt.where(Expense.occurred_at >= from_dt)
    if to_date is not None:
        to_dt = datetime.combine(to_date, datetime.max.time(), tzinfo=UTC)
        stmt = stmt.where(Expense.occurred_at <= to_dt)
        count_stmt = count_stmt.where(Expense.occurred_at <= to_dt)
    if category_id is not None:
        stmt = stmt.where(Expense.category_id == category_id)
        count_stmt = count_stmt.where(Expense.category_id == category_id)

    stmt = stmt.order_by(Expense.occurred_at.desc(), Expense.id.desc()).limit(limit).offset(offset)

    items = (await session.execute(stmt)).scalars().all()
    total = await session.scalar(count_stmt) or 0
    return list(items), int(total)


async def get_expense(session: AsyncSession, user: User, expense_id: int) -> Expense:
    expense = await session.get(Expense, expense_id)
    if expense is None:
        raise ExpenseNotFoundError(expense_id)
    if expense.user_id != user.id:
        raise ExpenseForbiddenError(expense_id)
    return expense


async def update_expense(
    session: AsyncSession, user: User, expense_id: int, payload: ExpenseUpdate
) -> Expense:
    expense = await session.get(Expense, expense_id)
    if expense is None:
        raise ExpenseNotFoundError(expense_id)
    if expense.user_id != user.id:
        raise ExpenseForbiddenError(expense_id)

    expense.amount = payload.amount
    expense.currency = payload.currency
    # amount_base mirrors amount until multi-currency conversion lands.
    expense.amount_base = payload.amount
    expense.description = payload.description
    if payload.category_id is not None:
        expense.category_id = payload.category_id
    if payload.occurred_at is not None:
        expense.occurred_at = payload.occurred_at
    if payload.source is not None:
        expense.source = payload.source
    expense.is_business = payload.is_business

    await session.commit()
    await session.refresh(expense)
    return expense


async def delete_expense(session: AsyncSession, user: User, expense_id: int) -> None:
    expense = await session.get(Expense, expense_id)
    if expense is None:
        raise ExpenseNotFoundError(expense_id)
    if expense.user_id != user.id:
        raise ExpenseForbiddenError(expense_id)
    await session.delete(expense)
    await session.commit()
