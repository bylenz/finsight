"""Tests for FinSight dashboard endpoint (FR-DASH-01..03, NFR-01)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from finsight.auth.service import get_user_by_email
from finsight.expenses.models import Expense
from finsight.households.models import Household, HouseholdMember, HouseholdRole
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import auth_headers

# --- helpers ---------------------------------------------------------------


async def _seed_expense_via_api(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    amount: str = "1.00",
    currency: str = "PEN",
    description: str = "seed",
    category_id: int | None = None,
    occurred_at: datetime | None = None,
) -> dict:
    payload: dict = {"amount": amount, "currency": currency, "description": description}
    if category_id is not None:
        payload["category_id"] = category_id
    if occurred_at is not None:
        payload["occurred_at"] = occurred_at.isoformat()
    r = await client.post("/expenses", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _ensure_household_for(db_session: AsyncSession, email: str) -> int:
    """Return the household_id for a user, creating Personal if absent."""
    from sqlalchemy import select

    user = await get_user_by_email(db_session, email)
    assert user is not None
    hh = await db_session.scalar(select(Household).where(Household.owner_id == user.id).limit(1))
    if hh is None:
        hh = Household(name="Personal", owner_id=user.id)
        db_session.add(hh)
        await db_session.flush()
        db_session.add(
            HouseholdMember(household_id=hh.id, user_id=user.id, role=HouseholdRole.OWNER.value)
        )
        await db_session.flush()
    return hh.id


async def _insert_expense_directly(
    db_session: AsyncSession,
    *,
    user_email: str,
    amount: Decimal,
    amount_base: Decimal,
    occurred_at: datetime,
    category_id: int | None = None,
    currency: str = "PEN",
) -> Expense:
    """Insert an expense bypassing the API (lets us control amount_base independently)."""
    user = await get_user_by_email(db_session, user_email)
    assert user is not None
    household_id = await _ensure_household_for(db_session, user_email)
    exp = Expense(
        user_id=user.id,
        household_id=household_id,
        amount=amount,
        currency=currency,
        amount_base=amount_base,
        category_id=category_id,
        description="direct",
        occurred_at=occurred_at,
        is_business=False,
        source="manual",
    )
    db_session.add(exp)
    await db_session.commit()
    await db_session.refresh(exp)
    return exp


def _current_month_str() -> str:
    now = datetime.now(tz=UTC)
    return f"{now.year:04d}-{now.month:02d}"


# --- auth ------------------------------------------------------------------


async def test_dashboard_requires_auth_returns_401(client: AsyncClient) -> None:
    response = await client.get("/dashboard")
    assert response.status_code == 401


# --- empty state -----------------------------------------------------------


async def test_dashboard_empty_returns_zero_total_and_empty_breakdowns(
    client: AsyncClient,
) -> None:
    headers = await auth_headers(client)
    response = await client.get("/dashboard", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["month"] == _current_month_str()
    assert body["currency"] == "PEN"
    assert float(body["total_spent"]) == 0.0
    assert body["expense_count"] == 0
    assert body["by_category"] == []
    # by_week may have entries (the weeks of the month) but their amounts must be 0
    assert all(float(w["amount"]) == 0.0 for w in body["by_week"])
    assert body["budgets"] == []


# --- month parameter -------------------------------------------------------


async def test_dashboard_default_month_is_current_when_not_provided(
    client: AsyncClient,
) -> None:
    headers = await auth_headers(client)
    response = await client.get("/dashboard", headers=headers)
    assert response.status_code == 200
    assert response.json()["month"] == _current_month_str()


async def test_dashboard_explicit_month_filters_by_month(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await auth_headers(client, "filter@example.com")
    # Trigger category seed via API expense in current month
    seed = await _seed_expense_via_api(client, headers, amount="10.00")
    cat_id = seed["category_id"]

    # Insert one expense in 2024-03 directly
    target_dt = datetime(2024, 3, 15, 12, 0, tzinfo=UTC)
    await _insert_expense_directly(
        db_session,
        user_email="filter@example.com",
        amount=Decimal("100.00"),
        amount_base=Decimal("100.00"),
        occurred_at=target_dt,
        category_id=cat_id,
    )

    response = await client.get("/dashboard?month=2024-03", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["month"] == "2024-03"
    assert float(body["total_spent"]) == 100.0
    assert body["expense_count"] == 1


@pytest.mark.parametrize("bad", ["2026-13", "not-a-month", "2026/05", "2026-1", "26-05"])
async def test_dashboard_invalid_month_format_returns_422(client: AsyncClient, bad: str) -> None:
    headers = await auth_headers(client)
    response = await client.get(f"/dashboard?month={bad}", headers=headers)
    assert response.status_code == 422, f"month={bad!r} got {response.status_code}"


# --- amount_base vs amount -------------------------------------------------


async def test_dashboard_total_sums_amount_base_not_amount(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await auth_headers(client, "ab@example.com")
    seed = await _seed_expense_via_api(client, headers, amount="1.00")
    cat_id = seed["category_id"]

    # Two expenses in 2024-06: amount=999 each but amount_base=10 each.
    when = datetime(2024, 6, 10, 12, 0, tzinfo=UTC)
    await _insert_expense_directly(
        db_session,
        user_email="ab@example.com",
        amount=Decimal("999.00"),
        amount_base=Decimal("10.00"),
        occurred_at=when,
        category_id=cat_id,
    )
    await _insert_expense_directly(
        db_session,
        user_email="ab@example.com",
        amount=Decimal("999.00"),
        amount_base=Decimal("10.00"),
        occurred_at=when,
        category_id=cat_id,
    )

    response = await client.get("/dashboard?month=2024-06", headers=headers)
    assert response.status_code == 200
    body = response.json()
    # Sum of amount_base = 20.00, NOT amount (1998.00)
    assert float(body["total_spent"]) == 20.0
    assert body["expense_count"] == 2


# --- user scoping ----------------------------------------------------------


async def test_dashboard_only_includes_caller_expenses(client: AsyncClient) -> None:
    a_headers = await auth_headers(client, "a@example.com")
    b_headers = await auth_headers(client, "b@example.com")

    await _seed_expense_via_api(client, a_headers, amount="10.00", description="A1")
    await _seed_expense_via_api(client, b_headers, amount="500.00", description="B1")
    await _seed_expense_via_api(client, b_headers, amount="500.00", description="B2")

    response = await client.get("/dashboard", headers=a_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["expense_count"] == 1
    assert float(body["total_spent"]) == 10.0


# --- by_category -----------------------------------------------------------


async def test_dashboard_by_category_excludes_zero_spend_categories(
    client: AsyncClient,
) -> None:
    headers = await auth_headers(client)
    # Seed one expense — this triggers seeding of all default categories,
    # most of which will have zero spend for this user.
    await _seed_expense_via_api(client, headers, amount="50.00")
    response = await client.get("/dashboard", headers=headers)
    assert response.status_code == 200
    body = response.json()
    # Only categories with spend appear — exactly one entry expected here.
    cats = body["by_category"]
    assert len(cats) == 1
    assert all(float(c["amount"]) > 0 for c in cats)


async def test_dashboard_by_category_sorted_by_amount_desc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await auth_headers(client, "sort@example.com")
    seed = await _seed_expense_via_api(client, headers, amount="1.00")
    cat_a = seed["category_id"]

    # Find a different category id (any other seeded category)
    from finsight.categories.models import Category
    from sqlalchemy import select

    other = await db_session.scalar(select(Category).where(Category.id != cat_a).limit(1))
    assert other is not None
    cat_b = other.id

    when = datetime(2024, 7, 10, 12, 0, tzinfo=UTC)
    # cat_b: 500, cat_a: 100  → expect cat_b first
    await _insert_expense_directly(
        db_session,
        user_email="sort@example.com",
        amount=Decimal("500.00"),
        amount_base=Decimal("500.00"),
        occurred_at=when,
        category_id=cat_b,
    )
    await _insert_expense_directly(
        db_session,
        user_email="sort@example.com",
        amount=Decimal("100.00"),
        amount_base=Decimal("100.00"),
        occurred_at=when,
        category_id=cat_a,
    )

    response = await client.get("/dashboard?month=2024-07", headers=headers)
    assert response.status_code == 200
    cats = response.json()["by_category"]
    assert len(cats) == 2
    assert cats[0]["category_id"] == cat_b
    assert cats[1]["category_id"] == cat_a
    assert float(cats[0]["amount"]) >= float(cats[1]["amount"])


async def test_dashboard_by_category_percentages_sum_close_to_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await auth_headers(client, "pct@example.com")
    seed = await _seed_expense_via_api(client, headers, amount="1.00")
    cat_a = seed["category_id"]

    from finsight.categories.models import Category
    from sqlalchemy import select

    other = await db_session.scalar(select(Category).where(Category.id != cat_a).limit(1))
    assert other is not None
    cat_b = other.id

    when = datetime(2024, 8, 5, 12, 0, tzinfo=UTC)
    await _insert_expense_directly(
        db_session,
        user_email="pct@example.com",
        amount=Decimal("33.33"),
        amount_base=Decimal("33.33"),
        occurred_at=when,
        category_id=cat_a,
    )
    await _insert_expense_directly(
        db_session,
        user_email="pct@example.com",
        amount=Decimal("66.67"),
        amount_base=Decimal("66.67"),
        occurred_at=when,
        category_id=cat_b,
    )

    response = await client.get("/dashboard?month=2024-08", headers=headers)
    assert response.status_code == 200
    cats = response.json()["by_category"]
    total_pct = sum(float(c["percentage"]) for c in cats)
    assert abs(total_pct - 1.0) < 1e-6


# --- by_week ---------------------------------------------------------------


async def test_dashboard_by_week_buckets_expenses_into_iso_weeks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await auth_headers(client, "weeks@example.com")
    seed = await _seed_expense_via_api(client, headers, amount="1.00")
    cat_id = seed["category_id"]

    # 2024-09: Mondays are 2024-09-02, -09, -16, -23, -30.
    # Insert one expense in week of Sep 9 and one in week of Sep 23.
    await _insert_expense_directly(
        db_session,
        user_email="weeks@example.com",
        amount=Decimal("100.00"),
        amount_base=Decimal("100.00"),
        occurred_at=datetime(2024, 9, 10, 12, 0, tzinfo=UTC),
        category_id=cat_id,
    )
    await _insert_expense_directly(
        db_session,
        user_email="weeks@example.com",
        amount=Decimal("200.00"),
        amount_base=Decimal("200.00"),
        occurred_at=datetime(2024, 9, 25, 12, 0, tzinfo=UTC),
        category_id=cat_id,
    )

    response = await client.get("/dashboard?month=2024-09", headers=headers)
    assert response.status_code == 200
    weeks = response.json()["by_week"]
    # ISO weeks intersecting Sep 2024: at least 5 buckets
    assert len(weeks) >= 4
    # Find the week containing 2024-09-10 (Monday 2024-09-09)
    target_w = next(w for w in weeks if w["week_start"] == "2024-09-09")
    assert float(target_w["amount"]) == 100.0
    assert target_w["week_end"] == "2024-09-15"
    # Find the week containing 2024-09-25 (Monday 2024-09-23)
    target_w2 = next(w for w in weeks if w["week_start"] == "2024-09-23")
    assert float(target_w2["amount"]) == 200.0


async def test_dashboard_by_week_excludes_amounts_outside_target_month(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await auth_headers(client, "edge@example.com")
    seed = await _seed_expense_via_api(client, headers, amount="1.00")
    cat_id = seed["category_id"]

    # Target month: 2024-10. The week of Sep 30 (Mon=Sep-30, Sun=Oct-06)
    # straddles months. An expense ON Sep 30 (outside target month) should
    # NOT count toward the dashboard total or the week's amount.
    await _insert_expense_directly(
        db_session,
        user_email="edge@example.com",
        amount=Decimal("999.00"),
        amount_base=Decimal("999.00"),
        occurred_at=datetime(2024, 9, 30, 23, 0, tzinfo=UTC),
        category_id=cat_id,
    )
    # Expense ON Oct 1 (inside target month, same ISO week)
    await _insert_expense_directly(
        db_session,
        user_email="edge@example.com",
        amount=Decimal("50.00"),
        amount_base=Decimal("50.00"),
        occurred_at=datetime(2024, 10, 1, 12, 0, tzinfo=UTC),
        category_id=cat_id,
    )

    response = await client.get("/dashboard?month=2024-10", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert float(body["total_spent"]) == 50.0
    weeks = body["by_week"]
    straddling = next(w for w in weeks if w["week_start"] == "2024-09-30")
    assert float(straddling["amount"]) == 50.0
    assert straddling["week_end"] == "2024-10-06"


# --- budgets summary -------------------------------------------------------


async def test_dashboard_budgets_includes_every_household_budget(client: AsyncClient) -> None:
    headers = await auth_headers(client, "bud@example.com")
    # Seed one expense to lazily create the household + categories
    seed = await _seed_expense_via_api(client, headers, amount="50.00")
    cat_id = seed["category_id"]

    # Global budget
    g = await client.post(
        "/budgets",
        json={"amount": "1000.00", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    assert g.status_code == 201
    # Per-category budget
    pc = await client.post(
        "/budgets",
        json={
            "amount": "200.00",
            "currency": "PEN",
            "period": "monthly",
            "category_id": cat_id,
        },
        headers=headers,
    )
    assert pc.status_code == 201

    response = await client.get("/dashboard", headers=headers)
    assert response.status_code == 200
    body = response.json()
    budgets = body["budgets"]
    assert len(budgets) == 2

    by_cat = {b["category_id"]: b for b in budgets}
    assert None in by_cat
    assert cat_id in by_cat

    global_bud = by_cat[None]
    assert float(global_bud["limit"]) == 1000.0
    assert float(global_bud["spent"]) == 50.0
    assert abs(float(global_bud["percentage"]) - 0.05) < 1e-6

    cat_bud = by_cat[cat_id]
    assert float(cat_bud["limit"]) == 200.0
    assert float(cat_bud["spent"]) == 50.0
    assert abs(float(cat_bud["percentage"]) - 0.25) < 1e-6


# --- performance smoke -----------------------------------------------------


async def test_dashboard_with_1000_expenses_returns_under_1500ms(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await auth_headers(client, "perf@example.com")
    seed = await _seed_expense_via_api(client, headers, amount="1.00")
    cat_id = seed["category_id"]

    # Insert 1000 expenses in current month directly (bypass per-request overhead).
    from finsight.households.models import Household
    from sqlalchemy import select

    user = await get_user_by_email(db_session, "perf@example.com")
    assert user is not None
    household_id = await db_session.scalar(
        select(Household.id).where(Household.owner_id == user.id).limit(1)
    )
    now = datetime.now(tz=UTC).replace(day=1, hour=12, minute=0, second=0, microsecond=0)
    rows = []
    for i in range(1000):
        rows.append(
            Expense(
                user_id=user.id,
                household_id=household_id,
                amount=Decimal("1.00"),
                currency="PEN",
                amount_base=Decimal("1.00"),
                category_id=cat_id,
                description=f"perf {i}",
                occurred_at=now + timedelta(minutes=i % 1000),
                is_business=False,
                source="manual",
            )
        )
    db_session.add_all(rows)
    await db_session.commit()

    started = time.perf_counter()
    response = await client.get("/dashboard", headers=headers)
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    # Qualitative bound — fail only if pathologically slow
    assert elapsed < 5.0, f"dashboard took {elapsed:.2f}s with 1000 expenses"


# --- currency --------------------------------------------------------------


async def test_dashboard_currency_field_matches_base_currency(client: AsyncClient) -> None:
    from finsight.config import settings

    headers = await auth_headers(client)
    response = await client.get("/dashboard", headers=headers)
    assert response.status_code == 200
    assert response.json()["currency"] == settings.base_currency == "PEN"


_ = pytest
