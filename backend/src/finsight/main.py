from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from finsight import __version__
from finsight.auth.router import router as auth_router
from finsight.budgets.router import alerts_router, budgets_router
from finsight.common.ratelimit import limiter
from finsight.config import settings
from finsight.dashboard.router import router as dashboard_router
from finsight.expenses.router import router as expenses_router
from finsight.exports.router import router as exports_router


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Return 429 with a Retry-After header (required by the rate-limit spec).

    SlowAPI's built-in header injection is avoided because it can raise on some
    routes; we set Retry-After explicitly, defaulting to the 60s window.
    """
    retry_after = getattr(exc, "retry_after", None)
    response = JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
    response.headers["Retry-After"] = str(retry_after if retry_after is not None else 60)
    return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="FinSight API",
        version=__version__,
        description="AI-powered personal finance tracker for LATAM",
    )

    # Attach SlowAPI limiter — enabled/disabled per settings.rate_limit_enabled.
    # The limiter instance is imported from common.ratelimit so routers can
    # reference it without circular imports.
    app.state.limiter = limiter
    limiter.enabled = settings.rate_limit_enabled
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(auth_router)
    app.include_router(expenses_router)
    app.include_router(budgets_router)
    app.include_router(alerts_router)
    app.include_router(dashboard_router)
    app.include_router(exports_router)
    return app


app = create_app()
