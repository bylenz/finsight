from fastapi import FastAPI

from finsight import __version__
from finsight.auth.router import router as auth_router
from finsight.budgets.router import alerts_router, budgets_router
from finsight.dashboard.router import router as dashboard_router
from finsight.expenses.router import router as expenses_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="FinSight API",
        version=__version__,
        description="AI-powered personal finance tracker for LATAM",
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(auth_router)
    app.include_router(expenses_router)
    app.include_router(budgets_router)
    app.include_router(alerts_router)
    app.include_router(dashboard_router)
    return app


app = create_app()
