from collections.abc import AsyncIterator

# Import models so they register with Base.metadata before create_all.
# auth.models imports User + RevokedToken + RefreshToken (PR3).
# common.audit imports AuditLog (PR4).
import finsight.auth.models
import finsight.budgets.models
import finsight.categories.models
import finsight.common.audit
import finsight.expenses.models
import finsight.households.models
import finsight.insights.models  # noqa: F401
import pytest
from finsight.db import Base, get_session
from finsight.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
async def db_session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def refresh_token_factory(db_session: AsyncSession):
    """Factory fixture: creates a valid refresh token row and returns the encoded JWT.

    Usage::

        async def test_something(refresh_token_factory, db_session):
            encoded = await refresh_token_factory(user_id=1, subject="user@example.com")
    """
    from finsight.auth.service import issue_refresh_token

    async def _factory(user_id: int, subject: str) -> str:
        return await issue_refresh_token(db_session, user_id=user_id, subject=subject)

    return _factory
