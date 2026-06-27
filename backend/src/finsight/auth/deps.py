from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import User
from finsight.auth.security import JWTError, decode_access_token
from finsight.auth.service import get_user_by_email, is_token_revoked
from finsight.db import get_session

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise unauthorized from exc

    jti = payload.get("jti")
    email = payload.get("sub")
    if jti is None or email is None:
        raise unauthorized

    # A refresh token must NOT authenticate normal API requests.
    if payload.get("token_type") != "access":
        raise unauthorized

    if await is_token_revoked(session, jti):
        raise unauthorized

    user = await get_user_by_email(session, email)
    if user is None:
        raise unauthorized
    return user


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise unauthorized from exc
    # Only access tokens are valid bearer credentials.
    if payload.get("token_type") != "access":
        raise unauthorized
    return payload
