"""Smoke tests for ApiClient — backend is mocked via httpx.MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest
from finsight_ui.api_client import ApiClient, ApiError


def _client_with_transport(handler) -> ApiClient:
    transport = httpx.MockTransport(handler)
    client = ApiClient(base_url="http://test", token=None)
    # Replace the internal client with one bound to the mock transport.
    client._client.close()
    client._client = httpx.Client(base_url="http://test", transport=transport)
    return client


def test_login_posts_credentials_and_stores_token():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"access_token": "tok-123", "token_type": "bearer", "expires_in": 3600},
        )

    client = _client_with_transport(handler)
    data = client.login("a@b.com", "secret123")

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/auth/login")
    assert captured["body"] == {"email": "a@b.com", "password": "secret123"}
    assert data["access_token"] == "tok-123"
    assert client.token == "tok-123"


def test_authorized_request_sends_bearer_header():
    seen_headers: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(dict(request.headers))
        return httpx.Response(200, json={"id": 1, "email": "a@b.com"})

    client = _client_with_transport(handler)
    client.token = "tok-xyz"

    user = client.me()
    assert user == {"id": 1, "email": "a@b.com"}
    assert seen_headers.get("authorization") == "Bearer tok-xyz"


def test_non_2xx_raises_api_error_with_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid credentials"})

    client = _client_with_transport(handler)
    with pytest.raises(ApiError) as excinfo:
        client.login("a@b.com", "wrong")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid credentials"


def test_list_expenses_unwraps_items_and_drops_none_params():
    seen_params: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "items": [{"id": 1, "amount": "10.00", "currency": "PEN"}],
                "limit": 50,
                "offset": 0,
                "total": 1,
            },
        )

    client = _client_with_transport(handler)
    client.token = "t"
    items = client.list_expenses(limit=50, offset=0)

    assert isinstance(items, list)
    assert items[0]["id"] == 1
    assert "from_date" not in seen_params
    assert "to_date" not in seen_params
    assert "category_id" not in seen_params
    assert seen_params["limit"] == "50"


def test_get_csv_bytes_returns_raw_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/export/csv"
        return httpx.Response(200, content=b"id,amount\n1,10.00\n")

    client = _client_with_transport(handler)
    client.token = "t"
    blob = client.get_csv_bytes()
    assert blob == b"id,amount\n1,10.00\n"


def test_export_csv_url_omits_none_params():
    client = ApiClient(base_url="http://test", token="t")
    assert client.export_csv_url() == "http://test/export/csv"
    url = client.export_csv_url(category_id=3)
    assert url == "http://test/export/csv?category_id=3"
    client.close()
