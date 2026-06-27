"""PR3 — Refresh tokens: test suite (strict TDD, RED first).

Covers SC-3.1 through SC-3.7 from the spec.
"""

from datetime import UTC, datetime, timedelta

from finsight.config import settings
from freezegun import freeze_time
from httpx import AsyncClient
from jose import jwt

VALID_USER = {"email": "refresh@example.com", "password": "SuperSecret123"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_and_login(client: AsyncClient) -> dict:
    """Register a user and return the full login response body."""
    await client.post("/auth/register", json=VALID_USER)
    resp = await client.post("/auth/login", json=VALID_USER)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# SC-3.1 — Login issues both access + refresh tokens
# ---------------------------------------------------------------------------


async def test_login_returns_access_and_refresh_tokens(client: AsyncClient) -> None:
    """SC-3.1: POST /auth/login must return both access_token and refresh_token."""
    body = await _register_and_login(client)

    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"

    access_payload = jwt.decode(
        body["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    assert access_payload["token_type"] == "access"

    refresh_payload = jwt.decode(
        body["refresh_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    assert refresh_payload["token_type"] == "refresh"


async def test_access_token_expires_in_15_minutes(client: AsyncClient) -> None:
    """SC-3.1: access token exp ≈ now + 15 min."""
    body = await _register_and_login(client)

    payload = jwt.decode(
        body["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    expected = datetime.now(tz=UTC) + timedelta(minutes=15)
    delta = abs((expires_at - expected).total_seconds())
    assert delta < 60, f"Access token expiration drifted by {delta}s (expected ~15 min)"


async def test_refresh_token_expires_in_7_days(client: AsyncClient) -> None:
    """SC-3.1: refresh token exp ≈ now + 7 days."""
    body = await _register_and_login(client)

    payload = jwt.decode(
        body["refresh_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    expected = datetime.now(tz=UTC) + timedelta(days=7)
    delta = abs((expires_at - expected).total_seconds())
    assert delta < 60, f"Refresh token expiration drifted by {delta}s (expected ~7 days)"


# ---------------------------------------------------------------------------
# SC-3.2 — /auth/refresh rotates the refresh token and issues a new pair
# ---------------------------------------------------------------------------


async def test_refresh_issues_new_access_token(client: AsyncClient) -> None:
    """SC-3.2: POST /auth/refresh returns a new access_token."""
    body = await _register_and_login(client)
    refresh_token = body["refresh_token"]

    resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200, resp.text
    new_body = resp.json()

    assert "access_token" in new_body
    # The new access token must be a valid access token
    access_payload = jwt.decode(
        new_body["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    assert access_payload["token_type"] == "access"


async def test_refresh_rotates_refresh_token(client: AsyncClient) -> None:
    """SC-3.2: after /auth/refresh, old refresh token is revoked."""
    body = await _register_and_login(client)
    refresh_token = body["refresh_token"]

    resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200, resp.text

    # Using the old refresh token again must fail
    resp2 = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp2.status_code == 401


# ---------------------------------------------------------------------------
# SC-3.3 — Revoked refresh token is rejected
# ---------------------------------------------------------------------------


async def test_revoked_refresh_token_rejected(client: AsyncClient) -> None:
    """SC-3.3: a refresh token already rotated (revoked=True) must return 401."""
    body = await _register_and_login(client)
    old_refresh = body["refresh_token"]

    # Rotate once — old token becomes revoked
    r1 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r1.status_code == 200

    # Attempt to reuse the revoked token
    r2 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401


# ---------------------------------------------------------------------------
# SC-3.4 — Expired refresh token is rejected
# ---------------------------------------------------------------------------


async def test_expired_refresh_token_rejected(client: AsyncClient) -> None:
    """SC-3.4: an expired refresh token (simulated via freezegun) must return 401."""
    # Login in the past so the token is already expired when we call /refresh
    with freeze_time(datetime.now(tz=UTC) - timedelta(days=8)):
        body = await _register_and_login(client)

    refresh_token = body["refresh_token"]
    # Now in the present the token should be expired
    resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# SC-3.5 — Access token used on /auth/refresh is rejected
# ---------------------------------------------------------------------------


async def test_access_token_rejected_on_refresh_endpoint(client: AsyncClient) -> None:
    """SC-3.5: sending an access token to /auth/refresh must return 401."""
    body = await _register_and_login(client)
    access_token = body["access_token"]  # token_type == "access"

    resp = await client.post("/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# SC-3.6 — Access token expires after 15 minutes
# ---------------------------------------------------------------------------


async def test_access_token_expires_after_15_minutes(client: AsyncClient) -> None:
    """SC-3.6: an access token is rejected after 16 minutes (via freezegun)."""
    body = await _register_and_login(client)
    access_token = body["access_token"]

    # Advance time 16 minutes into the future
    with freeze_time(datetime.now(tz=UTC) + timedelta(minutes=16)):
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# SC-3.7 — Logout revokes the active refresh token
# ---------------------------------------------------------------------------


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    """SC-3.7: POST /auth/logout must revoke the active refresh tokens for the user."""
    body = await _register_and_login(client)
    access_token = body["access_token"]
    refresh_token = body["refresh_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    logout = await client.post("/auth/logout", headers=headers)
    assert logout.status_code == 204

    # After logout the refresh token must be rejected
    resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# R3.10 — A refresh token must NOT authenticate normal API requests
# ---------------------------------------------------------------------------


async def test_refresh_token_rejected_on_protected_endpoint(client: AsyncClient) -> None:
    """R3.10: using a refresh token as a Bearer credential must return 401."""
    body = await _register_and_login(client)
    refresh_token = body["refresh_token"]

    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert resp.status_code == 401
