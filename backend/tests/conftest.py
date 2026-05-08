import pytest
from finsight.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
