"""Tests for the AI insights endpoint (FR-IO-02).

The Anthropic client is mocked at the SDK boundary via monkeypatch on
``finsight.insights.categorizer._get_client`` — exactly like the categorizer
tests. The real API is NEVER called.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from tests.helpers import auth_headers

# --- helpers -----------------------------------------------------------------


def _fake_message(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def _install_fake_llm(monkeypatch: pytest.MonkeyPatch, text_or_exc: Any) -> AsyncMock:
    """Replace categorizer._get_client with a stub whose messages.create
    AsyncMock returns a fake message with ``text`` (or raises text_or_exc)."""
    from finsight.insights import categorizer

    create_mock = AsyncMock()
    if isinstance(text_or_exc, BaseException):
        create_mock.side_effect = text_or_exc
    else:
        create_mock.return_value = _fake_message(text_or_exc)

    fake_client = MagicMock()
    fake_client.messages.create = create_mock
    monkeypatch.setattr(categorizer, "_get_client", lambda: fake_client)
    monkeypatch.setattr(categorizer, "_api_key", lambda: "test-key")
    return create_mock


async def _seed_expense(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    amount: str = "50.00",
    description: str = "almuerzo",
) -> dict:
    body = {"amount": amount, "currency": "PEN", "description": description}
    r = await client.post("/expenses", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _current_month_str() -> str:
    now = datetime.now(tz=UTC)
    return f"{now.year:04d}-{now.month:02d}"


# --- auth --------------------------------------------------------------------


async def test_insights_requires_auth_returns_401(client: AsyncClient) -> None:
    response = await client.get("/insights")
    assert response.status_code == 401


# --- empty state -------------------------------------------------------------


async def test_insights_empty_month_returns_friendly_message_and_no_llm(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user with zero expenses gets an empty-state insight and the LLM is
    NEVER contacted (no wasted tokens / latency)."""
    from finsight.insights import categorizer

    sentinel = AsyncMock(side_effect=AssertionError("LLM must not be called on empty month"))
    fake_client = MagicMock()
    fake_client.messages.create = sentinel
    monkeypatch.setattr(categorizer, "_get_client", lambda: fake_client)
    monkeypatch.setattr(categorizer, "_api_key", lambda: "test-key")

    headers = await auth_headers(client, "empty@example.com")
    response = await client.get("/insights", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["month"] == _current_month_str()
    assert body["ai_generated"] is False
    assert body["summary"]  # non-empty message
    assert body["highlights"] == []
    assert sentinel.await_count == 0


# --- deterministic fallback (no API key) -------------------------------------


async def test_insights_without_api_key_returns_deterministic_fallback(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from finsight.insights import categorizer

    monkeypatch.setattr(categorizer, "_api_key", lambda: "")
    headers = await auth_headers(client, "nokey@example.com")
    await _seed_expense(client, headers, amount="100.00", description="mercado")

    response = await client.get("/insights", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai_generated"] is False
    assert "100" in body["summary"]
    assert body["currency"] == "PEN"


# --- LLM happy path ----------------------------------------------------------


async def test_insights_llm_happy_path_returns_ai_generated_insight(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await auth_headers(client, "ai@example.com")
    await _seed_expense(client, headers, amount="120.00", description="restaurante")

    payload = {
        "summary": "Tu gasto se concentra en comida.",
        "highlights": ["Reduce un 10% en Food.", "Cocina en casa los fines de semana."],
    }
    _install_fake_llm(monkeypatch, json.dumps(payload))

    response = await client.get("/insights", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai_generated"] is True
    assert body["summary"] == payload["summary"]
    assert body["highlights"] == payload["highlights"]


# --- LLM failure / unparseable ----------------------------------------------


async def test_insights_llm_failure_returns_fallback(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await auth_headers(client, "fail@example.com")
    await _seed_expense(client, headers, amount="80.00", description="taxi")

    _install_fake_llm(monkeypatch, ConnectionError("network down"))

    response = await client.get("/insights", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    # Failure is swallowed — deterministic fallback kicks in.
    assert body["ai_generated"] is False
    assert body["summary"]


async def test_insights_llm_unparseable_returns_fallback(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await auth_headers(client, "garbage@example.com")
    await _seed_expense(client, headers, amount="40.00", description="café")

    _install_fake_llm(monkeypatch, "esto no es json ni nada útil")

    response = await client.get("/insights", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai_generated"] is False
    assert body["summary"]


async def test_insights_llm_missing_summary_field_returns_fallback(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await auth_headers(client, "badfields@example.com")
    await _seed_expense(client, headers, amount="40.00", description="snack")

    # Valid JSON but missing the required "summary" key.
    _install_fake_llm(monkeypatch, json.dumps({"highlights": ["algo"]}))

    response = await client.get("/insights", headers=headers)
    assert response.status_code == 200
    assert response.json()["ai_generated"] is False


# --- misc --------------------------------------------------------------------


async def test_insights_default_month_is_current(client: AsyncClient) -> None:
    headers = await auth_headers(client, "month@example.com")
    response = await client.get("/insights", headers=headers)
    assert response.status_code == 200
    assert response.json()["month"] == _current_month_str()


@pytest.mark.parametrize("bad", ["2026-13", "not-a-month", "2026/05"])
async def test_insights_invalid_month_returns_422(client: AsyncClient, bad: str) -> None:
    headers = await auth_headers(client)
    response = await client.get(f"/insights?month={bad}", headers=headers)
    assert response.status_code == 422, f"month={bad!r} got {response.status_code}"


# Reference imports so linters don't complain.
_ = Decimal
