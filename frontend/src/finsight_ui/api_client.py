"""Typed HTTP client for the FinSight backend.

Thin wrapper over ``httpx.Client``. Methods return parsed JSON (``dict``/``list``)
and raise :class:`ApiError` on non-2xx responses so the page layer can
``st.error(err.detail)`` consistently.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DEFAULT_TIMEOUT = float(os.getenv("BACKEND_TIMEOUT", "10.0"))


class ApiError(Exception):
    """Raised when the backend returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str, *, payload: Any = None) -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail
        self.payload = payload


def _extract_detail(response: httpx.Response) -> tuple[str, Any]:
    """Best-effort extraction of a friendly error detail from a response."""
    try:
        payload = response.json()
    except ValueError:
        return response.text or response.reason_phrase, None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail, payload
        if isinstance(detail, list) and detail:
            # FastAPI 422 validation errors → first message
            first = detail[0]
            if isinstance(first, dict) and "msg" in first:
                return str(first["msg"]), payload
        return str(payload), payload
    return str(payload), payload


class ApiClient:
    """Small typed client over the FinSight backend.

    A single :class:`httpx.Client` is reused for the lifetime of the instance.
    Cleanup is delegated to ``httpx`` (the underlying connection pool closes on
    garbage collection); call :meth:`close` explicitly if you want to be sure.
    """

    def __init__(
        self,
        base_url: str = BACKEND_URL,
        token: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    # ---------------------------------------------------------------- helpers

    def close(self) -> None:
        self._client.close()

    def _headers(self, *, json_body: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        clean_params = None
        if params:
            clean_params = {k: v for k, v in params.items() if v is not None}
        response = self._client.request(
            method,
            path,
            params=clean_params,
            json=json,
            headers=self._headers(json_body=json is not None),
        )
        if response.status_code >= 400:
            detail, payload = _extract_detail(response)
            raise ApiError(response.status_code, detail, payload=payload)
        return response

    @staticmethod
    def _iso_date(value: date | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _iso_datetime(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    # ------------------------------------------------------------------ auth

    def register(self, email: str, password: str) -> dict:
        response = self._request(
            "POST", "/auth/register", json={"email": email, "password": password}
        )
        return response.json()

    def login(self, email: str, password: str) -> dict:
        response = self._request("POST", "/auth/login", json={"email": email, "password": password})
        data = response.json()
        # Bind the token to this client so subsequent calls are authenticated.
        token = data.get("access_token")
        if token:
            self.token = token
        return data

    def logout(self) -> None:
        self._request("POST", "/auth/logout")
        self.token = None

    def me(self) -> dict:
        return self._request("GET", "/auth/me").json()

    # -------------------------------------------------------------- expenses

    def list_expenses(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        from_date: date | None = None,
        to_date: date | None = None,
        category_id: int | None = None,
    ) -> list[dict]:
        params = {
            "limit": limit,
            "offset": offset,
            "from_date": self._iso_date(from_date),
            "to_date": self._iso_date(to_date),
            "category_id": category_id,
        }
        response = self._request("GET", "/expenses", params=params)
        payload = response.json()
        if isinstance(payload, dict) and "items" in payload:
            return list(payload["items"])
        # Fallback (unexpected shape) — return as-is if it's already a list.
        return list(payload) if isinstance(payload, list) else []

    def create_expense(
        self,
        *,
        amount: float,
        currency: str,
        description: str | None = None,
        occurred_at: datetime | None = None,
        category_id: int | None = None,
        is_business: bool = False,
    ) -> dict:
        body: dict[str, Any] = {
            "amount": float(amount),
            "currency": currency,
            "is_business": is_business,
        }
        if description is not None:
            body["description"] = description
        if occurred_at is not None:
            body["occurred_at"] = self._iso_datetime(occurred_at)
        if category_id is not None:
            body["category_id"] = category_id
        return self._request("POST", "/expenses", json=body).json()

    def update_expense(self, expense_id: int, **fields: Any) -> dict:
        body = dict(fields)
        if "occurred_at" in body and isinstance(body["occurred_at"], datetime):
            body["occurred_at"] = self._iso_datetime(body["occurred_at"])
        return self._request("PUT", f"/expenses/{expense_id}", json=body).json()

    def delete_expense(self, expense_id: int) -> None:
        self._request("DELETE", f"/expenses/{expense_id}")

    # --------------------------------------------------------------- budgets

    def list_budgets(self) -> list[dict]:
        return self._request("GET", "/budgets").json()

    def create_budget(
        self,
        *,
        amount: float,
        currency: str,
        category_id: int | None,
        period: str = "monthly",
    ) -> dict:
        body = {
            "amount": float(amount),
            "currency": currency,
            "category_id": category_id,
            "period": period,
        }
        return self._request("POST", "/budgets", json=body).json()

    def update_budget(self, budget_id: int, **fields: Any) -> dict:
        return self._request("PUT", f"/budgets/{budget_id}", json=dict(fields)).json()

    def delete_budget(self, budget_id: int) -> None:
        self._request("DELETE", f"/budgets/{budget_id}")

    def budget_status(self, budget_id: int) -> dict:
        return self._request("GET", f"/budgets/{budget_id}/status").json()

    # ------------------------------------------------------------ categories

    def get_categories(self) -> list[dict]:
        return self._request("GET", "/categories").json()

    # ------------------------------------------------------------- dashboard

    def get_dashboard(self, month: str | None = None) -> dict:
        params = {"month": month} if month else None
        return self._request("GET", "/dashboard", params=params).json()

    # ---------------------------------------------------------------- alerts

    def list_alerts(self) -> list[dict]:
        return self._request("GET", "/alerts").json()

    # ---------------------------------------------------------------- export

    def export_csv_url(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        category_id: int | None = None,
    ) -> str:
        params = {
            "from": self._iso_date(from_date),
            "to": self._iso_date(to_date),
            "category_id": category_id,
        }
        clean = {k: v for k, v in params.items() if v is not None}
        qs = f"?{urlencode(clean)}" if clean else ""
        return f"{self.base_url}/export/csv{qs}"

    def get_csv_bytes(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        category_id: int | None = None,
    ) -> bytes:
        params = {
            "from": self._iso_date(from_date),
            "to": self._iso_date(to_date),
            "category_id": category_id,
        }
        clean_params = {k: v for k, v in params.items() if v is not None}
        response = self._client.get(
            "/export/csv",
            params=clean_params,
            headers=self._headers(json_body=False),
        )
        if response.status_code >= 400:
            detail, payload = _extract_detail(response)
            raise ApiError(response.status_code, detail, payload=payload)
        return response.content
