from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import RevokedToken, User
from finsight.auth.security import hash_password, verify_password


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise EmailAlreadyRegisteredError(email)

    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


async def revoke_token(session: AsyncSession, jti: str, expires_at: datetime) -> None:
    session.add(RevokedToken(jti=jti, expires_at=expires_at))
    await session.commit()


async def is_token_revoked(session: AsyncSession, jti: str) -> bool:
    result = await session.scalar(select(RevokedToken).where(RevokedToken.jti == jti))
    return result is not None


def utc_from_timestamp(ts: int | float) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)
