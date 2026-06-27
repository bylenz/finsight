import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from finsight.config import settings

_BCRYPT_ROUNDS = 12
_BCRYPT_MAX_BYTES = 72


def _truncate(plain: str) -> bytes:
    # bcrypt silently truncates beyond 72 bytes — be explicit so behavior is deterministic.
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(_truncate(plain), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_truncate(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(tz=UTC) + (
        expires_delta or timedelta(minutes=settings.jwt_expires_minutes)
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(tz=UTC),
        "token_type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, expires_delta: timedelta | None = None) -> tuple[str, str]:
    """Issue a refresh token.

    Returns ``(encoded_jwt, jti)`` so callers can persist the jti in the DB
    without decoding the token again.
    """
    jti = str(uuid.uuid4())
    expire = datetime.now(tz=UTC) + (
        expires_delta or timedelta(days=settings.jwt_refresh_expires_days)
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "jti": jti,
        "iat": datetime.now(tz=UTC),
        "token_type": "refresh",
    }
    encoded = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded, jti


def decode_token(token: str) -> dict:
    """Decode and validate signature + expiry. Raises JWTError on failure."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# Backward-compatible alias.
decode_access_token = decode_token


__all__ = [
    "JWTError",
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_token",
    "hash_password",
    "verify_password",
]
