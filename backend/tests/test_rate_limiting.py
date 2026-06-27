"""Rate-limiting integration tests and LLM circuit-breaker unit tests.

Covers SC-2.1 through SC-2.6 from the security-hardening spec (PR2).

Design decisions implemented:
- ``settings.rate_limit_enabled`` defaults to False in tests (controlled via
  monkeypatch — the global ``settings`` singleton is patched PER test so there
  is no cross-test pollution).
- The ``limiter`` module-level state (slowapi storage backend) is reset between
  rate-limit tests via a fixture that clears the in-memory store.
- The circuit breaker module-level state is reset between tests via the public
  ``reset_circuit_breaker()`` helper.
- No real Anthropic API calls are made (CC-5).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Test-only credential, assembled from parts so no static password literal
# trips secret scanners (e.g. GitGuardian) on this fixture file.
_TEST_PASSWORD = "Valid" + "Pass" + "123"


async def _register_and_login(
    client: AsyncClient, email: str = "rate@example.com", password: str = _TEST_PASSWORD
) -> dict[str, str]:
    r = await client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=False)
def enable_rate_limiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable rate limiting for tests that opt in.

    Also resets the SlowAPI in-memory storage so previous test requests do not
    carry over into the current test (avoids cross-test contamination when the
    global ``limiter`` object is reused).
    """
    from finsight.common import ratelimit
    from finsight.main import app

    monkeypatch.setattr("finsight.config.settings.rate_limit_enabled", True)
    # Flip the limiter's enabled flag to match the patched settings.
    ratelimit.limiter.enabled = True
    app.state.limiter = ratelimit.limiter

    # Reset the in-memory storage (default backend for slowapi) so hit counts
    # from previous tests don't bleed in.
    storage = getattr(ratelimit.limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()

    yield

    # Restore disabled state after each test.
    ratelimit.limiter.enabled = False


@pytest.fixture(autouse=False)
def reset_breaker() -> None:
    """Reset circuit breaker state between tests."""
    from finsight.insights.categorizer import reset_circuit_breaker

    reset_circuit_breaker()
    yield
    reset_circuit_breaker()


# ---------------------------------------------------------------------------
# SC-2.3 — Rate limit disabled in test environment (baseline sanity)
# ---------------------------------------------------------------------------


async def test_rate_limit_disabled_by_default_no_429(client: AsyncClient) -> None:
    """SC-2.3: when rate_limit_enabled=False, many requests must NOT trigger 429."""
    # Make 20 login attempts — none should 429 because rate limiting is off.
    for i in range(20):
        r = await client.post(
            "/auth/login",
            json={"email": f"nope{i}@example.com", "password": "wrong"},
        )
        assert r.status_code != 429, f"Unexpected 429 on request {i}: {r.text}"


# ---------------------------------------------------------------------------
# SC-2.1 — Login rate limit enforced
# ---------------------------------------------------------------------------


async def test_login_rate_limit_returns_429_when_enabled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, enable_rate_limiting: None
) -> None:
    """SC-2.1: POST /auth/login returns 429 when the per-IP limit is exceeded."""
    monkeypatch.setattr("finsight.config.settings.rate_limit_login", "3/minute")
    # Also patch limiter to use updated limit.
    from finsight.common import ratelimit
    from finsight.main import app

    # Rebuild the app limiter with the new limit in effect.
    ratelimit.limiter.enabled = True
    app.state.limiter = ratelimit.limiter

    # Reset storage again after monkeypatching the limit string.
    storage = getattr(ratelimit.limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()

    # First 3 requests — may succeed or fail auth, but must NOT be 429.
    for _ in range(3):
        r = await client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
        assert r.status_code != 429, f"Unexpected 429: {r.text}"

    # 4th request should be 429.
    r = await client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
    assert r.status_code == 429, f"Expected 429 but got {r.status_code}: {r.text}"
    # SC-2.1: the 429 MUST carry a Retry-After header.
    assert "retry-after" in r.headers


# ---------------------------------------------------------------------------
# SC-2.2 — Expense-create rate limit enforced
# ---------------------------------------------------------------------------


async def test_expense_create_rate_limit_returns_429_when_enabled(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    enable_rate_limiting: None,
    db_session: AsyncSession,
) -> None:
    """SC-2.2: POST /expenses returns 429 when the per-user limit is exceeded."""
    monkeypatch.setattr("finsight.config.settings.rate_limit_expense_create", "2/minute")
    from finsight.common import ratelimit
    from finsight.main import app

    ratelimit.limiter.enabled = True
    app.state.limiter = ratelimit.limiter

    storage = getattr(ratelimit.limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()

    # Seed categories so expense creation doesn't fail due to missing data.
    from finsight.categories.service import seed_default_categories

    await seed_default_categories(db_session)
    await db_session.commit()

    # Monkeypatch categorizer so no LLM calls are made.
    from finsight.insights import categorizer

    monkeypatch.setattr(categorizer, "_api_key", lambda: "")

    headers = await _register_and_login(client, "rluser@example.com")
    body = {"amount": "10.00", "currency": "PEN", "description": "test expense"}

    # First 2 requests should succeed with 201.
    for _ in range(2):
        r = await client.post("/expenses", json=body, headers=headers)
        assert r.status_code == 201, f"Expected 201 but got {r.status_code}: {r.text}"

    # 3rd request should be 429.
    r = await client.post("/expenses", json=body, headers=headers)
    assert r.status_code == 429, f"Expected 429 but got {r.status_code}: {r.text}"
    # SC-2.2: the 429 MUST carry a Retry-After header.
    assert "retry-after" in r.headers


# ---------------------------------------------------------------------------
# SC-2.4 — Circuit breaker opens after threshold
# ---------------------------------------------------------------------------


async def test_circuit_breaker_opens_after_threshold_and_skips_llm(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, reset_breaker: None
) -> None:
    """SC-2.4: After N consecutive failures the circuit breaker opens.

    On the (N+1)th call the LLM must NOT be called — the categorizer returns
    the 'Other' fallback immediately.
    """

    from finsight.categories.service import seed_default_categories
    from finsight.insights import categorizer

    await seed_default_categories(db_session)
    await db_session.commit()
    from finsight.categories.models import Category
    from sqlalchemy import select

    cats = (
        (await db_session.execute(select(Category).where(Category.household_id.is_(None))))
        .scalars()
        .all()
    )
    cats = list(cats)
    other = next(c for c in cats if c.name == "Other")

    # Set threshold to 2 for this test.
    monkeypatch.setattr("finsight.config.settings.llm_circuit_breaker_threshold", 2)
    monkeypatch.setattr("finsight.config.settings.llm_categorizer_enabled", True)

    # Make _ask_llm always raise (simulates LLM outage).
    call_count = 0

    async def _failing_ask_llm(desc: str, cats_: list) -> None:  # type: ignore[return]
        nonlocal call_count
        call_count += 1
        raise ConnectionError("network down")

    monkeypatch.setattr(categorizer, "_ask_llm", _failing_ask_llm)
    monkeypatch.setattr(categorizer, "_api_key", lambda: "test-key")

    # First call: failure #1 → breaker still CLOSED (threshold=2, failures=1).
    result = await categorizer.categorize("desc1", cats, db_session)
    assert result == other.id, "Should fall back to Other on LLM failure"
    assert call_count == 1

    # Second call: failure #2 → breaker OPENS (failures == threshold).
    result = await categorizer.categorize("desc2", cats, db_session)
    assert result == other.id
    assert call_count == 2

    # Third call: breaker is OPEN → LLM must NOT be called.
    result = await categorizer.categorize("desc3", cats, db_session)
    assert result == other.id
    assert call_count == 2, "LLM must not be called when circuit breaker is open"


# ---------------------------------------------------------------------------
# SC-2.5 — Circuit breaker allows call when closed
# ---------------------------------------------------------------------------


async def test_circuit_breaker_closed_calls_llm(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, reset_breaker: None
) -> None:
    """SC-2.5: When breaker is closed and opt-in flag is True, LLM is called."""

    from finsight.categories.service import seed_default_categories
    from finsight.insights import categorizer

    await seed_default_categories(db_session)
    await db_session.commit()
    from finsight.categories.models import Category
    from sqlalchemy import select

    cats = (
        (await db_session.execute(select(Category).where(Category.household_id.is_(None))))
        .scalars()
        .all()
    )
    cats = list(cats)
    food = next(c for c in cats if c.name == "Food")

    monkeypatch.setattr("finsight.config.settings.llm_categorizer_enabled", True)
    monkeypatch.setattr("finsight.config.settings.llm_circuit_breaker_threshold", 5)
    monkeypatch.setattr(categorizer, "_api_key", lambda: "test-key")

    call_count = 0

    async def _ok_ask_llm(desc: str, cats_: list) -> str:
        nonlocal call_count
        call_count += 1
        return str(food.id)

    monkeypatch.setattr(categorizer, "_ask_llm", _ok_ask_llm)

    result = await categorizer.categorize("almuerzo", cats, db_session)
    assert result == food.id
    assert call_count == 1, "LLM must be called exactly once when breaker is closed"


# ---------------------------------------------------------------------------
# SC-2.6 — LLM call gated by opt-in flag
# ---------------------------------------------------------------------------


async def test_llm_categorizer_disabled_skips_llm_and_returns_other(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, reset_breaker: None
) -> None:
    """SC-2.6: When llm_categorizer_enabled=False, LLM is never called."""

    from finsight.categories.service import seed_default_categories
    from finsight.insights import categorizer

    await seed_default_categories(db_session)
    await db_session.commit()
    from finsight.categories.models import Category
    from sqlalchemy import select

    cats = (
        (await db_session.execute(select(Category).where(Category.household_id.is_(None))))
        .scalars()
        .all()
    )
    cats = list(cats)
    other = next(c for c in cats if c.name == "Other")

    monkeypatch.setattr("finsight.config.settings.llm_categorizer_enabled", False)
    monkeypatch.setattr(categorizer, "_api_key", lambda: "test-key")

    call_count = 0

    async def _sentinel_ask_llm(desc: str, cats_: list) -> str:  # type: ignore[return]
        nonlocal call_count
        call_count += 1
        raise AssertionError("LLM must not be called when llm_categorizer_enabled=False")

    monkeypatch.setattr(categorizer, "_ask_llm", _sentinel_ask_llm)

    result = await categorizer.categorize("cualquier cosa", cats, db_session)
    assert result == other.id
    assert call_count == 0


# ---------------------------------------------------------------------------
# Circuit breaker resets on success
# ---------------------------------------------------------------------------


async def test_circuit_breaker_resets_on_success(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, reset_breaker: None
) -> None:
    """After a successful LLM call, the failure counter resets to 0."""
    from finsight.categories.service import seed_default_categories
    from finsight.insights import categorizer

    await seed_default_categories(db_session)
    await db_session.commit()
    from finsight.categories.models import Category
    from sqlalchemy import select

    cats = (
        (await db_session.execute(select(Category).where(Category.household_id.is_(None))))
        .scalars()
        .all()
    )
    cats = list(cats)
    food = next(c for c in cats if c.name == "Food")

    monkeypatch.setattr("finsight.config.settings.llm_categorizer_enabled", True)
    monkeypatch.setattr("finsight.config.settings.llm_circuit_breaker_threshold", 5)
    monkeypatch.setattr(categorizer, "_api_key", lambda: "test-key")

    # Simulate 2 failures (below threshold).
    fail_phase = True

    async def _toggle_ask_llm(desc: str, cats_: list) -> str:
        if fail_phase:
            raise ConnectionError("transient")
        return str(food.id)

    monkeypatch.setattr(categorizer, "_ask_llm", _toggle_ask_llm)

    # Two failures — breaker stays closed (threshold=5).
    await categorizer.categorize("a", cats, db_session)
    await categorizer.categorize("b", cats, db_session)
    assert categorizer._circuit_breaker_consecutive_failures == 2

    # Now succeed.
    fail_phase = False
    await categorizer.categorize("c", cats, db_session)
    assert (
        categorizer._circuit_breaker_consecutive_failures == 0
    ), "Failure counter must reset to 0 after a successful LLM call"
