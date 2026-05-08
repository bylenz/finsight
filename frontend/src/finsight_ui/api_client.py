import os

import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


class ApiClient:
    def __init__(self, base_url: str = BACKEND_URL, token: str | None = None) -> None:
        self.base_url = base_url
        self.token = token

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def get(self, path: str, **params: object) -> httpx.Response:
        return httpx.get(f"{self.base_url}{path}", headers=self._headers(), params=params)

    def post(self, path: str, json: dict | None = None) -> httpx.Response:
        return httpx.post(f"{self.base_url}{path}", headers=self._headers(), json=json)
