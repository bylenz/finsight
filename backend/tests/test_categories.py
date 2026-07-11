"""Tests for FinSight GET /categories endpoint."""

from __future__ import annotations

from finsight.categories.models import Category
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import auth_headers

DEFAULT_CATEGORY_NAMES = {
    "Food",
    "Transport",
    "Housing",
    "Health",
    "Entertainment",
    "Education",
    "Shopping",
    "Bills",
    "Other",
}


async def test_list_categories_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/categories")
    assert response.status_code == 401


async def test_list_categories_returns_global_defaults(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    response = await client.get("/categories", headers=headers)
    assert response.status_code == 200, response.text

    body = response.json()
    names = {c["name"] for c in body}
    assert DEFAULT_CATEGORY_NAMES.issubset(names)
    for c in body:
        assert set(c.keys()) == {"id", "name", "household_id"}


async def test_list_categories_includes_household_category_but_not_other_households(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await auth_headers(client, email="bob@example.com")

    # Trigger creation of bob's personal household + global category seeding.
    seed = await client.post(
        "/expenses",
        json={"amount": "1.00", "currency": "PEN", "description": "seed"},
        headers=headers,
    )
    assert seed.status_code == 201, seed.text
    bob_household_id = seed.json()["household_id"]

    own_cat = Category(name="Bob Only", icon="🔒", color="#111111", household_id=bob_household_id)
    other_cat = Category(
        name="Other Household Only", icon="🚫", color="#222222", household_id=999999
    )
    db_session.add_all([own_cat, other_cat])
    await db_session.commit()

    response = await client.get("/categories", headers=headers)
    assert response.status_code == 200, response.text
    names = {c["name"] for c in response.json()}

    assert "Bob Only" in names
    assert "Other Household Only" not in names


async def test_list_categories_ids_match_db(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await auth_headers(client, email="carol@example.com")
    response = await client.get("/categories", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    db_ids = set(
        (await db_session.execute(select(Category.id).where(Category.household_id.is_(None))))
        .scalars()
        .all()
    )
    returned_ids = {c["id"] for c in body}
    assert db_ids.issubset(returned_ids)
