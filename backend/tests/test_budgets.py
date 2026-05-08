"""Tests for FinSight budgets CRUD + status (FR-BUD-01..02)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.helpers import auth_headers


async def _seed_expense_and_get_category(client: AsyncClient, headers: dict[str, str]) -> int:
    """Create one expense to trigger category seeding and return its category_id."""
    r = await client.post(
        "/expenses",
        json={"amount": "1.00", "currency": "PEN", "description": "seed"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["category_id"]


# --- POST /budgets -----------------------------------------------------------


async def test_create_budget_global_returns_201(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.post(
        "/budgets",
        json={"amount": "1000.00", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] > 0
    assert body["amount"] == "1000.00"
    assert body["currency"] == "PEN"
    assert body["period"] == "monthly"
    assert body["category_id"] is None


async def test_create_budget_per_category_returns_201(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    cat_id = await _seed_expense_and_get_category(client, headers)
    response = await client.post(
        "/budgets",
        json={
            "amount": "500.00",
            "currency": "USD",
            "period": "monthly",
            "category_id": cat_id,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["category_id"] == cat_id


async def test_create_budget_amount_must_be_positive(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.post(
        "/budgets",
        json={"amount": "0", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    assert response.status_code == 422

    response = await client.post(
        "/budgets",
        json={"amount": "-10", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_budget_invalid_currency(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.post(
        "/budgets",
        json={"amount": "100", "currency": "EUR", "period": "monthly"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_budget_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/budgets",
        json={"amount": "100", "currency": "PEN", "period": "monthly"},
    )
    assert response.status_code == 401


# --- GET /budgets ------------------------------------------------------------


async def test_list_budgets_returns_only_caller_household(client: AsyncClient) -> None:
    a_headers = await auth_headers(client, "a@example.com")
    b_headers = await auth_headers(client, "b@example.com")

    await client.post(
        "/budgets",
        json={"amount": "100", "currency": "PEN", "period": "monthly"},
        headers=a_headers,
    )
    await client.post(
        "/budgets",
        json={"amount": "200", "currency": "PEN", "period": "monthly"},
        headers=b_headers,
    )

    response = await client.get("/budgets", headers=a_headers)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["amount"] == "100.00"


async def test_list_budgets_filter_by_category(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    cat_id = await _seed_expense_and_get_category(client, headers)
    # Global budget
    await client.post(
        "/budgets",
        json={"amount": "1000", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    # Per-category budget
    await client.post(
        "/budgets",
        json={
            "amount": "300",
            "currency": "PEN",
            "period": "monthly",
            "category_id": cat_id,
        },
        headers=headers,
    )

    response = await client.get(f"/budgets?category_id={cat_id}", headers=headers)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["category_id"] == cat_id


# --- GET /budgets/{id} -------------------------------------------------------


async def test_get_budget_owner_returns_200(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    created = await client.post(
        "/budgets",
        json={"amount": "100", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    budget_id = created.json()["id"]
    response = await client.get(f"/budgets/{budget_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == budget_id


async def test_get_budget_not_owner_returns_403(client: AsyncClient) -> None:
    a_headers = await auth_headers(client, "a@example.com")
    b_headers = await auth_headers(client, "b@example.com")
    created = await client.post(
        "/budgets",
        json={"amount": "100", "currency": "PEN", "period": "monthly"},
        headers=a_headers,
    )
    budget_id = created.json()["id"]
    response = await client.get(f"/budgets/{budget_id}", headers=b_headers)
    assert response.status_code == 403


async def test_get_budget_404_when_missing(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get("/budgets/9999", headers=headers)
    assert response.status_code == 404


# --- PUT /budgets/{id} -------------------------------------------------------


async def test_update_budget_amount(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    created = await client.post(
        "/budgets",
        json={"amount": "100", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    budget_id = created.json()["id"]
    response = await client.put(
        f"/budgets/{budget_id}",
        json={"amount": "999.99", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["amount"] == "999.99"


async def test_update_budget_not_owner_returns_403(client: AsyncClient) -> None:
    a_headers = await auth_headers(client, "a@example.com")
    b_headers = await auth_headers(client, "b@example.com")
    created = await client.post(
        "/budgets",
        json={"amount": "100", "currency": "PEN", "period": "monthly"},
        headers=a_headers,
    )
    budget_id = created.json()["id"]
    response = await client.put(
        f"/budgets/{budget_id}",
        json={"amount": "1", "currency": "PEN", "period": "monthly"},
        headers=b_headers,
    )
    assert response.status_code == 403


# --- DELETE /budgets/{id} ----------------------------------------------------


async def test_delete_budget_returns_204(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    created = await client.post(
        "/budgets",
        json={"amount": "100", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    budget_id = created.json()["id"]
    response = await client.delete(f"/budgets/{budget_id}", headers=headers)
    assert response.status_code == 204
    after = await client.get(f"/budgets/{budget_id}", headers=headers)
    assert after.status_code == 404


# --- GET /budgets/{id}/status -----------------------------------------------


async def test_budget_status_global_basic(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    # global budget = 100
    created = await client.post(
        "/budgets",
        json={"amount": "100", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    budget_id = created.json()["id"]
    # spend 30
    await client.post(
        "/expenses",
        json={"amount": "30", "currency": "PEN", "description": "x"},
        headers=headers,
    )

    response = await client.get(f"/budgets/{budget_id}/status", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert float(body["spent"]) == 30.0
    assert float(body["limit"]) == 100.0
    assert abs(float(body["percentage"]) - 0.30) < 1e-6
    assert body["currency"] == "PEN"


async def test_budget_status_excludes_previous_months(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    created = await client.post(
        "/budgets",
        json={"amount": "100", "currency": "PEN", "period": "monthly"},
        headers=headers,
    )
    budget_id = created.json()["id"]

    # An expense from 60 days ago — should NOT count
    last_month = (datetime.now(tz=UTC) - timedelta(days=60)).isoformat()
    await client.post(
        "/expenses",
        json={
            "amount": "999",
            "currency": "PEN",
            "description": "old",
            "occurred_at": last_month,
        },
        headers=headers,
    )
    # Current month expense
    await client.post(
        "/expenses",
        json={"amount": "10", "currency": "PEN", "description": "now"},
        headers=headers,
    )

    response = await client.get(f"/budgets/{budget_id}/status", headers=headers)
    assert response.status_code == 200
    assert float(response.json()["spent"]) == 10.0


async def test_budget_status_per_category_only_counts_matching(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    cat_a = await _seed_expense_and_get_category(client, headers)

    # Build a per-category budget for cat_a
    created = await client.post(
        "/budgets",
        json={
            "amount": "100",
            "currency": "PEN",
            "period": "monthly",
            "category_id": cat_a,
        },
        headers=headers,
    )
    budget_id = created.json()["id"]

    # Already 1.00 spent on cat_a from seeding. Add another in cat_a.
    await client.post(
        "/expenses",
        json={
            "amount": "20",
            "currency": "PEN",
            "description": "cat-a hit",
            "category_id": cat_a,
        },
        headers=headers,
    )

    response = await client.get(f"/budgets/{budget_id}/status", headers=headers)
    assert response.status_code == 200
    # Should be 1.00 (seed) + 20.00 = 21.00
    assert float(response.json()["spent"]) == 21.0


async def test_budget_status_not_owner_returns_403(client: AsyncClient) -> None:
    a_headers = await auth_headers(client, "a@example.com")
    b_headers = await auth_headers(client, "b@example.com")
    created = await client.post(
        "/budgets",
        json={"amount": "100", "currency": "PEN", "period": "monthly"},
        headers=a_headers,
    )
    budget_id = created.json()["id"]
    response = await client.get(f"/budgets/{budget_id}/status", headers=b_headers)
    assert response.status_code == 403


_ = pytest
