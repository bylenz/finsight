"""HTTP endpoints for budgets and alerts."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.deps import get_current_user
from finsight.auth.models import User
from finsight.budgets import alerts as alert_service
from finsight.budgets import service as budget_service
from finsight.budgets.schemas import (
    AlertPublic,
    BudgetCreate,
    BudgetPublic,
    BudgetStatus,
    BudgetUpdate,
)
from finsight.budgets.service import BudgetForbiddenError, BudgetNotFoundError
from finsight.common.audit import emit_audit_event
from finsight.db import get_session

budgets_router = APIRouter(prefix="/budgets", tags=["budgets"])
alerts_router = APIRouter(prefix="/alerts", tags=["alerts"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@budgets_router.post("", response_model=BudgetPublic, status_code=status.HTTP_201_CREATED)
async def create_budget_endpoint(
    payload: BudgetCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BudgetPublic:
    budget = await budget_service.create_budget(session, user, payload)
    await emit_audit_event(
        "budget_created",
        user_id=user.id,
        ip=request.client.host if request.client else None,
        outcome="success",
        session=session,
        metadata={"resource_id": budget.id, "resource_type": "budget"},
    )
    return BudgetPublic.model_validate(budget)


@budgets_router.get("", response_model=list[BudgetPublic])
async def list_budgets_endpoint(
    category_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[BudgetPublic]:
    items = await budget_service.list_budgets(session, user, category_id=category_id)
    return [BudgetPublic.model_validate(b) for b in items]


@budgets_router.get("/{budget_id}", response_model=BudgetPublic)
async def get_budget_endpoint(
    budget_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BudgetPublic:
    try:
        budget = await budget_service.get_budget(session, user, budget_id)
    except BudgetNotFoundError as exc:
        raise _not_found() from exc
    except BudgetForbiddenError as exc:
        raise _forbidden() from exc
    return BudgetPublic.model_validate(budget)


@budgets_router.put("/{budget_id}", response_model=BudgetPublic)
async def update_budget_endpoint(
    budget_id: int,
    payload: BudgetUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BudgetPublic:
    try:
        budget = await budget_service.update_budget(session, user, budget_id, payload)
    except BudgetNotFoundError as exc:
        raise _not_found() from exc
    except BudgetForbiddenError as exc:
        raise _forbidden() from exc
    await emit_audit_event(
        "budget_updated",
        user_id=user.id,
        ip=request.client.host if request.client else None,
        outcome="success",
        session=session,
        metadata={"resource_id": budget_id, "resource_type": "budget"},
    )
    return BudgetPublic.model_validate(budget)


@budgets_router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_endpoint(
    budget_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        await budget_service.delete_budget(session, user, budget_id)
    except BudgetNotFoundError as exc:
        raise _not_found() from exc
    except BudgetForbiddenError as exc:
        raise _forbidden() from exc
    await emit_audit_event(
        "budget_deleted",
        user_id=user.id,
        ip=request.client.host if request.client else None,
        outcome="success",
        session=session,
        metadata={"resource_id": budget_id, "resource_type": "budget"},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@budgets_router.get("/{budget_id}/status", response_model=BudgetStatus)
async def get_budget_status_endpoint(
    budget_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BudgetStatus:
    try:
        spent, limit, percentage, currency = await budget_service.get_budget_status(
            session, user, budget_id
        )
    except BudgetNotFoundError as exc:
        raise _not_found() from exc
    except BudgetForbiddenError as exc:
        raise _forbidden() from exc
    return BudgetStatus(spent=spent, limit=limit, percentage=percentage, currency=currency)


@alerts_router.get("", response_model=list[AlertPublic])
async def list_alerts_endpoint(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[AlertPublic]:
    items = await alert_service.list_alerts_for_user(session, user)
    return [AlertPublic.model_validate(a) for a in items]
