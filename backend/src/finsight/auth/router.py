from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.deps import get_current_user, get_token_payload
from finsight.auth.models import User
from finsight.auth.schemas import TokenResponse, UserLogin, UserPublic, UserRegister
from finsight.auth.security import create_access_token
from finsight.auth.service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    authenticate_user,
    register_user,
    revoke_token,
    utc_from_timestamp,
)
from finsight.common.ratelimit import limiter
from finsight.config import settings
from finsight.db import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: UserRegister, session: AsyncSession = Depends(get_session)) -> User:
    try:
        return await register_user(session, payload.email, payload.password)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc


@router.post("/login", response_model=TokenResponse)
@limiter.limit(lambda: settings.rate_limit_login)
async def login(
    request: Request,
    payload: UserLogin,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    try:
        user = await authenticate_user(session, payload.email, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    token = create_access_token(subject=user.email)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expires_hours * 3600,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: dict = Depends(get_token_payload),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await revoke_token(session, jti=payload["jti"], expires_at=utc_from_timestamp(payload["exp"]))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserPublic)
async def me(current: User = Depends(get_current_user)) -> User:
    return current
