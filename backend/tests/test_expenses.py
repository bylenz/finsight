"""Tests for FinSight expenses CRUD endpoints (FR-EXP-01, FR-EXP-03, FR-EXP-04)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient


async def _register_and_login(
    client: AsyncClient, email: str, password: str = "SuperSecret123"
) -> str:
    reg = await client.post("/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 201, reg.text
    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


async def auth_headers(client: AsyncClient, email: str = "alice@example.com") -> dict[str, str]:
    token = await _register_and_login(client, email)
    return {"Authorization": f"Bearer {token}"}


VALID_BODY = {
    "amount": "12.50",
    "currency": "PEN",
    "description": "Lunch at corner cafe",
}


# --- POST /expenses ----------------------------------------------------------


async def test_create_expense_returns_201_and_body(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.post("/expenses", json=VALID_BODY, headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] > 0
    assert body["amount"] == "12.50"
    assert body["currency"] == "PEN"
    assert body["description"] == "Lunch at corner cafe"
    assert body["source"] == "manual"
    assert body["category_id"] is not None  # auto-assigned to "Other"


async def test_create_expense_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/expenses", json=VALID_BODY)
    assert response.status_code == 401


async def test_create_expense_amount_must_be_positive(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.post(
        "/expenses",
        json={**VALID_BODY, "amount": "0"},
        headers=headers,
    )
    assert response.status_code == 422

    response = await client.post(
        "/expenses",
        json={**VALID_BODY, "amount": "-5"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_expense_invalid_currency(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.post(
        "/expenses",
        json={**VALID_BODY, "currency": "EUR"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_expense_defaults_occurred_at_to_now(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    before = datetime.now(tz=UTC)
    response = await client.post("/expenses", json=VALID_BODY, headers=headers)
    assert response.status_code == 201
    occurred_at = datetime.fromisoformat(response.json()["occurred_at"])
    delta = abs((occurred_at - before).total_seconds())
    assert delta < 60, f"occurred_at drifted by {delta}s"


async def test_create_expense_defaults_source_to_manual(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.post("/expenses", json=VALID_BODY, headers=headers)
    assert response.status_code == 201
    assert response.json()["source"] == "manual"


async def test_create_expense_with_explicit_category_id(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    # Create one to discover a real category id from the seeded set
    first = await client.post("/expenses", json=VALID_BODY, headers=headers)
    category_id = first.json()["category_id"]

    response = await client.post(
        "/expenses",
        json={**VALID_BODY, "category_id": category_id, "description": "Override"},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["category_id"] == category_id


async def test_create_expense_description_too_long_returns_422(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.post(
        "/expenses",
        json={**VALID_BODY, "description": "x" * 256},
        headers=headers,
    )
    assert response.status_code == 422


# --- GET /expenses (list) ----------------------------------------------------


async def test_list_expenses_returns_only_caller_expenses(client: AsyncClient) -> None:
    a_headers = await auth_headers(client, "a@example.com")
    b_headers = await auth_headers(client, "b@example.com")

    await client.post(
        "/expenses",
        json={**VALID_BODY, "description": "A's expense"},
        headers=a_headers,
    )
    await client.post(
        "/expenses",
        json={**VALID_BODY, "description": "B's expense"},
        headers=b_headers,
    )

    response = await client.get("/expenses", headers=a_headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["description"] == "A's expense"


async def test_list_expenses_pagination(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    for i in range(3):
        r = await client.post(
            "/expenses",
            json={**VALID_BODY, "description": f"E{i}"},
            headers=headers,
        )
        assert r.status_code == 201

    page1 = await client.get("/expenses?limit=2&offset=0", headers=headers)
    assert page1.status_code == 200
    assert len(page1.json()["items"]) == 2

    page2 = await client.get("/expenses?limit=2&offset=2", headers=headers)
    assert page2.status_code == 200
    assert len(page2.json()["items"]) == 1


async def test_list_expenses_filter_by_category(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    # First create one to get a valid category_id
    first = await client.post("/expenses", json=VALID_BODY, headers=headers)
    cat_id = first.json()["category_id"]

    # Create a second expense with a different (overridden) category — pick another.
    # We don't know other ids, so create one with same id then filter.
    await client.post(
        "/expenses",
        json={**VALID_BODY, "description": "match", "category_id": cat_id},
        headers=headers,
    )

    response = await client.get(f"/expenses?category_id={cat_id}", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 2
    assert all(item["category_id"] == cat_id for item in items)


async def test_list_expenses_filter_by_date_range(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    today = datetime.now(tz=UTC)
    yesterday = (today - timedelta(days=1)).isoformat()
    last_week = (today - timedelta(days=7)).isoformat()

    await client.post(
        "/expenses",
        json={**VALID_BODY, "description": "old", "occurred_at": last_week},
        headers=headers,
    )
    await client.post(
        "/expenses",
        json={**VALID_BODY, "description": "recent", "occurred_at": yesterday},
        headers=headers,
    )

    from_param = (today - timedelta(days=2)).date().isoformat()
    response = await client.get(f"/expenses?from_date={from_param}", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["description"] == "recent"


# --- GET /expenses/{id} ------------------------------------------------------


async def test_get_expense_by_id_owner_returns_200(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    created = await client.post("/expenses", json=VALID_BODY, headers=headers)
    expense_id = created.json()["id"]

    response = await client.get(f"/expenses/{expense_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == expense_id


async def test_get_expense_by_id_not_owner_returns_403(client: AsyncClient) -> None:
    a_headers = await auth_headers(client, "a@example.com")
    b_headers = await auth_headers(client, "b@example.com")
    created = await client.post("/expenses", json=VALID_BODY, headers=a_headers)
    expense_id = created.json()["id"]

    response = await client.get(f"/expenses/{expense_id}", headers=b_headers)
    assert response.status_code == 403


async def test_get_expense_404_when_missing(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get("/expenses/9999", headers=headers)
    assert response.status_code == 404


# --- PUT /expenses/{id} ------------------------------------------------------


async def test_update_expense_owner_returns_200(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    created = await client.post("/expenses", json=VALID_BODY, headers=headers)
    expense_id = created.json()["id"]

    response = await client.put(
        f"/expenses/{expense_id}",
        json={"amount": "99.99", "currency": "USD", "description": "Updated"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["amount"] == "99.99"
    assert body["currency"] == "USD"
    assert body["description"] == "Updated"


async def test_update_expense_not_owner_returns_403(client: AsyncClient) -> None:
    a_headers = await auth_headers(client, "a@example.com")
    b_headers = await auth_headers(client, "b@example.com")
    created = await client.post("/expenses", json=VALID_BODY, headers=a_headers)
    expense_id = created.json()["id"]

    response = await client.put(
        f"/expenses/{expense_id}",
        json={"amount": "1.00", "currency": "PEN", "description": "Hijack"},
        headers=b_headers,
    )
    assert response.status_code == 403


async def test_update_expense_404_when_missing(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.put(
        "/expenses/9999",
        json={"amount": "1.00", "currency": "PEN", "description": "Ghost"},
        headers=headers,
    )
    assert response.status_code == 404


# --- DELETE /expenses/{id} ---------------------------------------------------


async def test_delete_expense_owner_returns_204(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    created = await client.post("/expenses", json=VALID_BODY, headers=headers)
    expense_id = created.json()["id"]

    response = await client.delete(f"/expenses/{expense_id}", headers=headers)
    assert response.status_code == 204

    after = await client.get(f"/expenses/{expense_id}", headers=headers)
    assert after.status_code == 404


async def test_delete_expense_not_owner_returns_403(client: AsyncClient) -> None:
    a_headers = await auth_headers(client, "a@example.com")
    b_headers = await auth_headers(client, "b@example.com")
    created = await client.post("/expenses", json=VALID_BODY, headers=a_headers)
    expense_id = created.json()["id"]

    response = await client.delete(f"/expenses/{expense_id}", headers=b_headers)
    assert response.status_code == 403


async def test_delete_expense_returns_404_when_missing(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.delete("/expenses/9999", headers=headers)
    assert response.status_code == 404


# Avoid pytest "unused import" complaints for marker-style modules.
_ = pytest
