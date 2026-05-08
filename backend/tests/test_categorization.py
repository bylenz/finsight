"""Tests for AI auto-categorization (FR-EXP-02, FR-EXP-03, NFR-02).

These tests MUST never call the real Anthropic API. The Anthropic client is
mocked at the SDK boundary via monkeypatch on
`finsight.insights.categorizer._get_client`.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.categories.models import Category
from finsight.categories.service import seed_default_categories


# --- Helpers -----------------------------------------------------------------


def _fake_message(text: str) -> MagicMock:
    """Build a fake Anthropic Message response: response.content[0].text == text."""
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def _install_fake_client(monkeypatch: pytest.MonkeyPatch, text_or_exc: Any) -> AsyncMock:
    """Replace categorizer._get_client with one that returns a stub whose
    messages.create AsyncMock returns _fake_message(text) or raises text_or_exc.

    Returns the AsyncMock standing in for messages.create, so tests can assert
    call counts and arguments.
    """
    from finsight.insights import categorizer

    create_mock = AsyncMock()
    if isinstance(text_or_exc, BaseException):
        create_mock.side_effect = text_or_exc
    else:
        create_mock.return_value = _fake_message(text_or_exc)

    fake_client = MagicMock()
    fake_client.messages.create = create_mock

    monkeypatch.setattr(categorizer, "_get_client", lambda: fake_client)
    # Make sure settings appear to have a key so the fast-fail path doesn't
    # short-circuit unless a test explicitly wants that.
    monkeypatch.setattr(categorizer, "_api_key", lambda: "test-key")
    return create_mock


async def _seed_and_get_categories(session: AsyncSession) -> list[Category]:
    await seed_default_categories(session)
    await session.commit()
    rows = (
        (await session.execute(select(Category).where(Category.household_id.is_(None))))
        .scalars()
        .all()
    )
    return list(rows)


async def _register_and_login(client: AsyncClient, email: str = "cat@example.com") -> dict[str, str]:
    pwd = "SuperSecret123"
    r = await client.post("/auth/register", json={"email": email, "password": pwd})
    assert r.status_code == 201, r.text
    login = await client.post("/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# --- Direct categorizer tests (db_session) -----------------------------------


async def test_categorize_calls_llm_on_cache_miss_and_caches_result(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finsight.insights import categorizer
    from finsight.insights.models import CategoryCache

    cats = await _seed_and_get_categories(db_session)
    food = next(c for c in cats if c.name == "Food")

    create_mock = _install_fake_client(monkeypatch, str(food.id))

    chosen = await categorizer.categorize("Almuerzo en la calle", cats, db_session)
    assert chosen == food.id
    assert create_mock.await_count == 1

    # Cache row exists keyed on normalized description
    cache_row = await db_session.scalar(
        select(CategoryCache).where(CategoryCache.normalized_description == "almuerzo en la calle")
    )
    assert cache_row is not None
    assert cache_row.category_id == food.id


async def test_categorize_returns_cached_value_on_hit_without_calling_llm(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finsight.insights import categorizer

    cats = await _seed_and_get_categories(db_session)
    transport = next(c for c in cats if c.name == "Transport")

    create_mock = _install_fake_client(monkeypatch, str(transport.id))

    first = await categorizer.categorize("Uber al aeropuerto", cats, db_session)
    second = await categorizer.categorize("Uber al aeropuerto", cats, db_session)

    assert first == second == transport.id
    assert create_mock.await_count == 1  # second call hit cache


async def test_categorize_normalizes_description_for_cache_lookup(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finsight.insights import categorizer

    cats = await _seed_and_get_categories(db_session)
    food = next(c for c in cats if c.name == "Food")

    create_mock = _install_fake_client(monkeypatch, str(food.id))

    a = await categorizer.categorize("  Almuerzo  ", cats, db_session)
    b = await categorizer.categorize("almuerzo", cats, db_session)
    c = await categorizer.categorize("ALMUERZO", cats, db_session)
    d = await categorizer.categorize("Almuerzo\t \tcon  amigos", cats, db_session)

    assert a == b == c == food.id
    # First three normalize to "almuerzo" -> 1 LLM call.
    # Fourth normalizes to "almuerzo con amigos" -> 1 more LLM call.
    assert create_mock.await_count == 2
    assert d == food.id


async def test_categorize_falls_back_to_other_when_llm_raises(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from finsight.insights import categorizer

    cats = await _seed_and_get_categories(db_session)
    other = next(c for c in cats if c.name == "Other")

    _install_fake_client(monkeypatch, ConnectionError("network down"))

    with caplog.at_level(logging.WARNING, logger="finsight.insights.categorizer"):
        chosen = await categorizer.categorize("Algo random", cats, db_session)

    assert chosen == other.id
    assert any("fallback" in rec.message.lower() or "llm" in rec.message.lower()
               for rec in caplog.records)


async def test_categorize_falls_back_to_other_when_llm_returns_unparseable(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finsight.insights import categorizer

    cats = await _seed_and_get_categories(db_session)
    other = next(c for c in cats if c.name == "Other")

    _install_fake_client(monkeypatch, "not-a-number lol")

    chosen = await categorizer.categorize("Cosa rara", cats, db_session)
    assert chosen == other.id


async def test_categorize_falls_back_to_other_when_id_not_in_available_set(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finsight.insights import categorizer

    cats = await _seed_and_get_categories(db_session)
    other = next(c for c in cats if c.name == "Other")

    # LLM hallucinates a non-existent id
    _install_fake_client(monkeypatch, "999999")

    chosen = await categorizer.categorize("desconocido", cats, db_session)
    assert chosen == other.id


async def test_categorize_falls_back_to_other_when_api_key_missing(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finsight.insights import categorizer

    cats = await _seed_and_get_categories(db_session)
    other = next(c for c in cats if c.name == "Other")

    # No api key -> SDK must NOT be called.
    monkeypatch.setattr(categorizer, "_api_key", lambda: "")

    sentinel = AsyncMock(side_effect=AssertionError("SDK must not be called"))
    fake_client = MagicMock()
    fake_client.messages.create = sentinel
    monkeypatch.setattr(categorizer, "_get_client", lambda: fake_client)

    chosen = await categorizer.categorize("Cualquier cosa", cats, db_session)
    assert chosen == other.id
    assert sentinel.await_count == 0


async def test_cache_table_unique_on_normalized_description(
    db_session: AsyncSession,
) -> None:
    from finsight.insights.models import CategoryCache

    await _seed_and_get_categories(db_session)
    food_id = await db_session.scalar(
        select(Category.id).where(Category.household_id.is_(None), Category.name == "Food")
    )
    assert food_id is not None

    db_session.add(CategoryCache(normalized_description="almuerzo", category_id=food_id))
    await db_session.commit()

    db_session.add(CategoryCache(normalized_description="almuerzo", category_id=food_id))
    with pytest.raises(Exception):  # IntegrityError from unique PK
        await db_session.commit()
    await db_session.rollback()


async def test_categorize_only_considers_user_available_categories(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prompt sent to the LLM must contain ONLY the categories passed in,
    never categories from other households.
    """
    from finsight.insights import categorizer

    cats = await _seed_and_get_categories(db_session)
    food = next(c for c in cats if c.name == "Food")

    # Add a private category for *another* household — it must NOT leak.
    other_household_secret = Category(
        name="SecretFromOtherHousehold", icon="🤫", color="#000000", household_id=999
    )
    db_session.add(other_household_secret)
    await db_session.commit()

    create_mock = _install_fake_client(monkeypatch, str(food.id))

    await categorizer.categorize("comida thai", cats, db_session)

    assert create_mock.await_count == 1
    call_kwargs = create_mock.call_args.kwargs
    # Concatenate everything that was sent to the LLM and check leak
    full_prompt = repr(call_kwargs)
    assert "SecretFromOtherHousehold" not in full_prompt
    assert "Food" in full_prompt


# --- Endpoint integration tests ----------------------------------------------


async def test_create_expense_with_no_category_calls_categorizer(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /expenses without category_id -> categorizer is invoked."""
    from finsight.insights import categorizer

    # Pre-seed defaults so we can determine Food.id ahead of time
    await _seed_and_get_categories(db_session)
    food_id = await db_session.scalar(
        select(Category.id).where(Category.household_id.is_(None), Category.name == "Food")
    )
    assert food_id is not None

    create_mock = _install_fake_client(monkeypatch, str(food_id))

    headers = await _register_and_login(client, "no-cat@example.com")
    body = {"amount": "20.00", "currency": "PEN", "description": "Pizza con amigos"}
    resp = await client.post("/expenses", json=body, headers=headers)
    assert resp.status_code == 201, resp.text

    assert create_mock.await_count == 1
    assert resp.json()["category_id"] == food_id


async def test_create_expense_with_explicit_category_skips_llm(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-EXP-03 manual override: explicit category_id -> NO LLM call."""
    from finsight.insights import categorizer

    await _seed_and_get_categories(db_session)
    transport_id = await db_session.scalar(
        select(Category.id).where(Category.household_id.is_(None), Category.name == "Transport")
    )
    assert transport_id is not None

    create_mock = _install_fake_client(monkeypatch, str(transport_id))

    headers = await _register_and_login(client, "explicit@example.com")
    body = {
        "amount": "15.00",
        "currency": "PEN",
        "description": "Whatever",
        "category_id": transport_id,
    }
    resp = await client.post("/expenses", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["category_id"] == transport_id
    assert create_mock.await_count == 0


async def test_create_expense_when_llm_unavailable_still_succeeds_with_other(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No api key set -> existing 'Other' fallback behaviour preserved."""
    from finsight.insights import categorizer

    monkeypatch.setattr(categorizer, "_api_key", lambda: "")

    headers = await _register_and_login(client, "no-key@example.com")
    body = {"amount": "9.99", "currency": "PEN", "description": "x"}
    resp = await client.post("/expenses", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["category_id"] is not None  # 'Other' fallback


# Reference imports so linters don't complain
_ = Decimal
