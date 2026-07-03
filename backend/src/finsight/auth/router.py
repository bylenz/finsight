from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.deps import get_current_user, get_token_payload
from finsight.auth.models import User
from finsight.auth.schemas import RefreshRequest, TokenResponse, UserLogin, UserPublic, UserRegister
from finsight.auth.security import create_access_token
from finsight.auth.service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    authenticate_user,
    get_user_by_email,
    issue_refresh_token,
    register_user,
    revoke_token,
    revoke_user_refresh_tokens,
    rotate_refresh_token,
    utc_from_timestamp,
)
from finsight.common.audit import emit_audit_event
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
    client_ip = request.client.host if request.client else None
    try:
        user = await authenticate_user(session, payload.email, payload.password)
    except InvalidCredentialsError as exc:
        await emit_audit_event(
            "login_failure", user_id=None, ip=client_ip, outcome="failure", session=session
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    access_token = create_access_token(subject=user.email)
    refresh_token_encoded = await issue_refresh_token(session, user_id=user.id, subject=user.email)

    await emit_audit_event(
        "login_success", user_id=user.id, ip=client_ip, outcome="success", session=session
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expires_minutes * 60,
        refresh_token=refresh_token_encoded,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Validate a refresh token, rotate it, and return a new access + refresh pair."""
    try:
        new_access, new_refresh = await rotate_refresh_token(session, payload.refresh_token)
    except InvalidRefreshTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    await emit_audit_event(
        "token_refresh",
        user_id=None,
        ip=request.client.host if request.client else None,
        outcome="success",
        session=session,
    )
    return TokenResponse(
        access_token=new_access,
        token_type="bearer",
        expires_in=settings.jwt_expires_minutes * 60,
        refresh_token=new_refresh,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    payload: dict = Depends(get_token_payload),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # Revoke the access token in the existing denylist
    await revoke_token(session, jti=payload["jti"], expires_at=utc_from_timestamp(payload["exp"]))

    # Revoke all active refresh tokens for this user
    user = await get_user_by_email(session, payload["sub"])
    if user is not None:
        await revoke_user_refresh_tokens(session, user.id)

    await emit_audit_event(
        "logout",
        user_id=user.id if user is not None else None,
        ip=request.client.host if request.client else None,
        outcome="success",
        session=session,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserPublic)
async def me(current: User = Depends(get_current_user)) -> User:
    return current
