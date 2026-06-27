"""SlowAPI rate-limiting integration for FinSight.

Exposes a single ``limiter`` instance that is attached to the FastAPI app in
``create_app()``.  Key function uses the authenticated user id when a valid JWT
is present in the Authorization header, falling back to the client IP address
so that unauthenticated endpoints (e.g. /auth/login) are still rate-limited per
IP.

When ``settings.rate_limit_enabled`` is ``False`` (the default in test
environments), the limiter is set to a no-op via the SlowAPI ``enabled``
toggle.  Dedicated rate-limit tests flip it on by monkeypatching the settings
before each request.
"""

from __future__ import annotations

import logging

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

logger = logging.getLogger(__name__)


def _rate_limit_key(request: Request) -> str:
    """Return user id from a valid JWT, else the client IP.

    This function must be synchronous — SlowAPI calls it outside an async
    context.  We read the Authorization header directly rather than calling
    ``get_current_user`` (which requires DB and async).
    """
    auth: str | None = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth[7:]
        try:
            from jose import jwt as _jwt

            from finsight.config import settings

            payload = _jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
                options={"verify_exp": False},  # expiry checked by dep
            )
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass  # fall through to IP
    return get_remote_address(request)


def _is_rate_limit_enabled() -> bool:
    from finsight.config import settings

    return settings.rate_limit_enabled


limiter = Limiter(key_func=_rate_limit_key, enabled=True)
