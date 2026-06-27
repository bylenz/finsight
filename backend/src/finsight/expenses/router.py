from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.deps import get_current_user
from finsight.auth.models import User
from finsight.common.ratelimit import limiter
from finsight.config import settings
from finsight.db import get_session
from finsight.expenses import service as expense_service
from finsight.expenses.schemas import (
    ExpenseCreate,
    ExpenseListResponse,
    ExpensePublic,
    ExpenseUpdate,
)
from finsight.expenses.service import ExpenseForbiddenError, ExpenseNotFoundError

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.post("", response_model=ExpensePublic, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: settings.rate_limit_expense_create)
async def create_expense_endpoint(
    request: Request,
    payload: ExpenseCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ExpensePublic:
    expense = await expense_service.create_expense(session, user, payload)
    return ExpensePublic.model_validate(expense)


@router.get("", response_model=ExpenseListResponse)
async def list_expenses_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    from_date: date | None = Query(default=None, alias="from_date"),
    to_date: date | None = Query(default=None, alias="to_date"),
    category_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ExpenseListResponse:
    items, total = await expense_service.list_expenses(
        session,
        user,
        limit=limit,
        offset=offset,
        from_date=from_date,
        to_date=to_date,
        category_id=category_id,
    )
    return ExpenseListResponse(
        items=[ExpensePublic.model_validate(e) for e in items],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.get("/{expense_id}", response_model=ExpensePublic)
async def get_expense_endpoint(
    expense_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ExpensePublic:
    try:
        expense = await expense_service.get_expense(session, user, expense_id)
    except ExpenseNotFoundError as exc:
        raise _not_found() from exc
    except ExpenseForbiddenError as exc:
        raise _forbidden() from exc
    return ExpensePublic.model_validate(expense)


@router.put("/{expense_id}", response_model=ExpensePublic)
async def update_expense_endpoint(
    expense_id: int,
    payload: ExpenseUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ExpensePublic:
    try:
        expense = await expense_service.update_expense(session, user, expense_id, payload)
    except ExpenseNotFoundError as exc:
        raise _not_found() from exc
    except ExpenseForbiddenError as exc:
        raise _forbidden() from exc
    return ExpensePublic.model_validate(expense)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense_endpoint(
    expense_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        await expense_service.delete_expense(session, user, expense_id)
    except ExpenseNotFoundError as exc:
        raise _not_found() from exc
    except ExpenseForbiddenError as exc:
        raise _forbidden() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
