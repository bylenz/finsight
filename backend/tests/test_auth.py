from datetime import UTC, datetime, timedelta

from finsight.auth.security import create_access_token
from finsight.config import settings
from httpx import AsyncClient
from jose import jwt

VALID_REGISTER = {"email": "camila@example.com", "password": "SuperSecret123"}


async def _register(client: AsyncClient, **overrides) -> dict:
    payload = {**VALID_REGISTER, **overrides}
    response = await client.post("/auth/register", json=payload)
    return response.json() if response.content else {}


# --- /auth/register ----------------------------------------------------------


async def test_register_creates_user_returns_201(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json=VALID_REGISTER)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == VALID_REGISTER["email"]
    assert "id" in body
    assert "password" not in body
    assert "password_hash" not in body


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    first = await client.post("/auth/register", json=VALID_REGISTER)
    assert first.status_code == 201
    second = await client.post("/auth/register", json=VALID_REGISTER)
    assert second.status_code == 409


async def test_register_invalid_email_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "SuperSecret123"},
    )
    assert response.status_code == 422


async def test_register_weak_password_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": "weak@example.com", "password": "short"},
    )
    assert response.status_code == 422


# --- /auth/login -------------------------------------------------------------


async def test_login_valid_credentials_returns_jwt(client: AsyncClient) -> None:
    await _register(client)
    response = await client.post(
        "/auth/login",
        json={"email": VALID_REGISTER["email"], "password": VALID_REGISTER["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    payload = jwt.decode(
        body["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    assert payload["sub"] == VALID_REGISTER["email"]
    assert "exp" in payload
    assert "jti" in payload


async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await _register(client)
    response = await client.post(
        "/auth/login",
        json={"email": VALID_REGISTER["email"], "password": "WrongPassword!"},
    )
    assert response.status_code == 401


async def test_login_unknown_user_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "Whatever123"},
    )
    assert response.status_code == 401


# --- /auth/me ----------------------------------------------------------------


async def test_me_with_valid_token_returns_user(client: AsyncClient) -> None:
    await _register(client)
    login = await client.post(
        "/auth/login",
        json={"email": VALID_REGISTER["email"], "password": VALID_REGISTER["password"]},
    )
    token = login.json()["access_token"]
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == VALID_REGISTER["email"]


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me")
    assert response.status_code == 401


async def test_me_with_expired_token_returns_401(client: AsyncClient) -> None:
    await _register(client)
    expired = create_access_token(
        subject=VALID_REGISTER["email"], expires_delta=timedelta(seconds=-1)
    )
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


async def test_me_with_garbage_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


# --- /auth/logout ------------------------------------------------------------


async def test_logout_invalidates_token(client: AsyncClient) -> None:
    await _register(client)
    login = await client.post(
        "/auth/login",
        json={"email": VALID_REGISTER["email"], "password": VALID_REGISTER["password"]},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_before = await client.get("/auth/me", headers=headers)
    assert me_before.status_code == 200

    logout = await client.post("/auth/logout", headers=headers)
    assert logout.status_code == 204

    me_after = await client.get("/auth/me", headers=headers)
    assert me_after.status_code == 401


async def test_logout_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/auth/logout")
    assert response.status_code == 401


# --- Token shape -------------------------------------------------------------


async def test_jwt_default_expires_in_15_minutes(client: AsyncClient) -> None:
    """Access token TTL changed to 15 min in PR3 (was 24 h)."""
    await _register(client)
    response = await client.post(
        "/auth/login",
        json={"email": VALID_REGISTER["email"], "password": VALID_REGISTER["password"]},
    )
    payload = jwt.decode(
        response.json()["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    expected = datetime.now(tz=UTC) + timedelta(minutes=15)
    delta = abs((expires_at - expected).total_seconds())
    assert delta < 60, f"Token expiration drifted by {delta}s (expected ~15 min)"
