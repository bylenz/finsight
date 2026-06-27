from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import RefreshToken, RevokedToken, User
from finsight.auth.security import (
    JWTError,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    """Raised when a refresh token is invalid, expired, or revoked."""


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


# ---------------------------------------------------------------------------
# Refresh token operations
# ---------------------------------------------------------------------------


async def issue_refresh_token(session: AsyncSession, user_id: int, subject: str) -> str:
    """Create a new refresh token, persist the row, and return the encoded JWT."""
    encoded, jti = create_refresh_token(subject=subject)
    from jose import jwt as _jwt

    from finsight.config import settings

    payload = _jwt.decode(encoded, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    expires_at = utc_from_timestamp(payload["exp"])
    session.add(
        RefreshToken(
            jti=jti,
            user_id=user_id,
            expires_at=expires_at,
        )
    )
    await session.commit()
    return encoded


async def rotate_refresh_token(
    session: AsyncSession, encoded_refresh_token: str
) -> tuple[str, str]:
    """Validate an existing refresh token and issue a new access + refresh pair.

    Returns ``(new_access_token, new_refresh_token_encoded)``.
    Raises ``InvalidRefreshTokenError`` on any validation failure.
    """
    from finsight.auth.security import create_access_token

    try:
        payload = decode_token(encoded_refresh_token)
    except JWTError as exc:
        raise InvalidRefreshTokenError("Invalid or expired refresh token") from exc

    if payload.get("token_type") != "refresh":
        raise InvalidRefreshTokenError("Token is not a refresh token")

    jti: str = payload["jti"]
    subject: str = payload["sub"]

    row = await session.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if row is None:
        raise InvalidRefreshTokenError("Refresh token not found in store")
    if row.revoked_at is not None:
        raise InvalidRefreshTokenError("Refresh token has been revoked")

    # Mark the old row as revoked
    row.revoked_at = datetime.now(tz=UTC)
    await session.flush()

    # Issue a new access token
    new_access = create_access_token(subject=subject)

    # Issue and persist a new refresh token
    new_refresh = await issue_refresh_token(session, user_id=row.user_id, subject=subject)

    return new_access, new_refresh


async def revoke_user_refresh_tokens(session: AsyncSession, user_id: int) -> None:
    """Mark ALL active (non-revoked) refresh tokens for a user as revoked.

    Called by /auth/logout.
    """
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    now = datetime.now(tz=UTC)
    for row in result.scalars():
        row.revoked_at = now
    await session.commit()
