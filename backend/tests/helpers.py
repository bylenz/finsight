"""Shared test helpers."""

from httpx import AsyncClient


async def register_and_login(
    client: AsyncClient, email: str, password: str = "SuperSecret123"
) -> str:
    reg = await client.post("/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 201, reg.text
    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


async def auth_headers(client: AsyncClient, email: str = "alice@example.com") -> dict[str, str]:
    token = await register_and_login(client, email)
    return {"Authorization": f"Bearer {token}"}
