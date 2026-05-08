"""Budget alerts — listing API.

Threshold evaluation lives alongside this module; it is wired into the
expense-create path so alerts surface as expenses land.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import User
from finsight.budgets.models import Alert


async def list_alerts_for_user(session: AsyncSession, user: User) -> list[Alert]:
    stmt = (
        select(Alert)
        .where(Alert.user_id == user.id)
        .order_by(Alert.triggered_at.desc(), Alert.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
