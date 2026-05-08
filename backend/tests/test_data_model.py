"""Tests for FinSight domain data model (households, categories, expenses, budgets, alerts).

Alert.type values: stored as strings "80" and "100" (str enum). CHECK constraint
restricts to exactly those two values.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from finsight.auth.models import User
from finsight.budgets.models import Alert, AlertType, Budget
from finsight.categories.models import Category
from finsight.categories.service import seed_default_categories
from finsight.expenses.models import Expense, ExpenseSource
from finsight.households.models import Household, HouseholdMember, HouseholdRole
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


async def _make_user(session, email="u1@example.com") -> User:
    user = User(email=email, password_hash="x")
    session.add(user)
    await session.flush()
    return user


async def _make_household(session, owner: User, name="Casa") -> Household:
    hh = Household(name=name, owner_id=owner.id)
    session.add(hh)
    await session.flush()
    return hh


# ---------- Household / HouseholdMember ----------


async def test_household_owner_relationship(db_session):
    user = await _make_user(db_session)
    hh = await _make_household(db_session, user, name="Hogar Lima")
    await db_session.commit()

    fetched = (
        await db_session.execute(select(Household).where(Household.id == hh.id))
    ).scalar_one()
    assert fetched.owner_id == user.id
    assert fetched.name == "Hogar Lima"
    assert fetched.created_at is not None


async def test_household_member_role_enum(db_session):
    user = await _make_user(db_session)
    hh = await _make_household(db_session, user)

    member = HouseholdMember(household_id=hh.id, user_id=user.id, role=HouseholdRole.OWNER.value)
    db_session.add(member)
    await db_session.commit()

    # invalid role must be rejected by CHECK constraint
    user2 = await _make_user(db_session, email="u2@example.com")
    bad = HouseholdMember(household_id=hh.id, user_id=user2.id, role="superadmin")
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_household_role_enum_accepts_all_three_values(db_session):
    owner = await _make_user(db_session, "owner@example.com")
    contrib = await _make_user(db_session, "c@example.com")
    viewer = await _make_user(db_session, "v@example.com")
    hh = await _make_household(db_session, owner)
    db_session.add_all(
        [
            HouseholdMember(household_id=hh.id, user_id=owner.id, role="owner"),
            HouseholdMember(household_id=hh.id, user_id=contrib.id, role="contributor"),
            HouseholdMember(household_id=hh.id, user_id=viewer.id, role="viewer"),
        ]
    )
    await db_session.commit()
    rows = (await db_session.execute(select(HouseholdMember))).scalars().all()
    assert {r.role for r in rows} == {"owner", "contributor", "viewer"}


# ---------- Category ----------


async def test_category_global_when_household_null(db_session):
    cat = Category(name="Coffee", icon="☕", color="#6F4E37", household_id=None)
    db_session.add(cat)
    await db_session.commit()

    fetched = (
        await db_session.execute(select(Category).where(Category.name == "Coffee"))
    ).scalar_one()
    assert fetched.household_id is None
    assert fetched.icon == "☕"


async def test_category_household_scoped(db_session):
    user = await _make_user(db_session)
    hh = await _make_household(db_session, user)
    cat = Category(name="Mascotas", icon="🐶", color="#A0522D", household_id=hh.id)
    db_session.add(cat)
    await db_session.commit()

    fetched = (
        await db_session.execute(select(Category).where(Category.name == "Mascotas"))
    ).scalar_one()
    assert fetched.household_id == hh.id


# ---------- Expense ----------


async def _make_expense(db_session, **overrides) -> Expense:
    user = overrides.pop("user", None) or await _make_user(
        db_session, email=f"u-{uuid.uuid4().hex[:8]}@example.com"
    )
    hh = overrides.pop("household", None) or await _make_household(db_session, user)
    cat = overrides.pop("category", None)
    if cat is None:
        cat = Category(name="Food", icon="🍔", color="#FF0000", household_id=None)
        db_session.add(cat)
        await db_session.flush()

    defaults = dict(
        user_id=user.id,
        household_id=hh.id,
        amount=Decimal("10.50"),
        currency="PEN",
        amount_base=Decimal("10.50"),
        category_id=cat.id,
        description="Lunch",
        occurred_at=_utcnow(),
        is_business=False,
        source="manual",
    )
    defaults.update(overrides)
    exp = Expense(**defaults)
    db_session.add(exp)
    return exp


async def test_expense_amount_must_be_positive(db_session):
    await _make_expense(db_session, amount=Decimal("0"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    await _make_expense(db_session, amount=Decimal("-5"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_expense_currency_check_pen_usd(db_session):
    # PEN ok
    await _make_expense(db_session, currency="PEN")
    await db_session.commit()
    # USD ok
    await _make_expense(db_session, currency="USD")
    await db_session.commit()
    # EUR rejected
    await _make_expense(db_session, currency="EUR")
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_expense_source_enum_values(db_session):
    for src in ("manual", "voice", "csv"):
        await _make_expense(db_session, source=src)
        await db_session.commit()

    await _make_expense(db_session, source="telepathy")
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_expense_source_enum_python(db_session):
    assert ExpenseSource.MANUAL.value == "manual"
    assert ExpenseSource.VOICE.value == "voice"
    assert ExpenseSource.CSV.value == "csv"


async def test_expense_user_occurred_at_index_exists():
    idx_columns = {tuple(c.name for c in idx.columns) for idx in Expense.__table__.indexes}
    assert ("user_id", "occurred_at") in idx_columns
    assert ("household_id", "occurred_at") in idx_columns


# ---------- Budget ----------


async def test_budget_amount_must_be_positive(db_session):
    user = await _make_user(db_session)
    hh = await _make_household(db_session, user)
    db_session.add(
        Budget(
            household_id=hh.id,
            category_id=None,
            amount=Decimal("0"),
            currency="PEN",
            period="monthly",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_budget_can_be_household_wide(db_session):
    user = await _make_user(db_session)
    hh = await _make_household(db_session, user)
    b = Budget(
        household_id=hh.id,
        category_id=None,
        amount=Decimal("1500.00"),
        currency="PEN",
        period="monthly",
    )
    db_session.add(b)
    await db_session.commit()
    fetched = (await db_session.execute(select(Budget))).scalar_one()
    assert fetched.category_id is None
    assert fetched.period == "monthly"


# ---------- Alert ----------


async def test_alert_type_check_80_or_100(db_session):
    user = await _make_user(db_session)
    hh = await _make_household(db_session, user)
    budget = Budget(
        household_id=hh.id,
        category_id=None,
        amount=Decimal("1000"),
        currency="PEN",
        period="monthly",
    )
    db_session.add(budget)
    await db_session.flush()

    # 80 ok
    db_session.add(Alert(user_id=user.id, budget_id=budget.id, type="80", triggered_at=_utcnow()))
    await db_session.commit()

    # 100 ok
    db_session.add(Alert(user_id=user.id, budget_id=budget.id, type="100", triggered_at=_utcnow()))
    await db_session.commit()

    # 50 rejected
    db_session.add(Alert(user_id=user.id, budget_id=budget.id, type="50", triggered_at=_utcnow()))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_alert_type_python_enum_values():
    assert AlertType.WARN_80.value == "80"
    assert AlertType.OVER_100.value == "100"


# ---------- Seed ----------


async def test_seed_default_categories_inserts_nine_global(db_session):
    inserted = await seed_default_categories(db_session)
    await db_session.commit()
    assert inserted == 9
    rows = (
        (await db_session.execute(select(Category).where(Category.household_id.is_(None))))
        .scalars()
        .all()
    )
    assert len(rows) == 9
    names = {r.name for r in rows}
    assert {
        "Food",
        "Transport",
        "Housing",
        "Health",
        "Entertainment",
        "Education",
        "Shopping",
        "Bills",
        "Other",
    } == names
    # all have icon and color
    assert all(r.icon and r.color for r in rows)


async def test_seed_default_categories_is_idempotent(db_session):
    first = await seed_default_categories(db_session)
    await db_session.commit()
    second = await seed_default_categories(db_session)
    await db_session.commit()
    assert first == 9
    assert second == 0
    count = len(
        (await db_session.execute(select(Category).where(Category.household_id.is_(None))))
        .scalars()
        .all()
    )
    assert count == 9
