from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.deps import get_current_user
from finsight.auth.models import User
from finsight.categories import service as category_service
from finsight.categories.schemas import CategoryPublic
from finsight.db import get_session

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryPublic])
async def list_categories_endpoint(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[CategoryPublic]:
    categories = await category_service.list_available_categories(session, user)
    return [CategoryPublic.model_validate(c) for c in categories]
