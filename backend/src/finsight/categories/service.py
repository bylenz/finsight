from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finsight.auth.models import User
from finsight.categories.models import Category

DEFAULT_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("Food", "🍔", "#E53935"),
    ("Transport", "🚌", "#1E88E5"),
    ("Housing", "🏠", "#6D4C41"),
    ("Health", "🏥", "#43A047"),
    ("Entertainment", "🎬", "#8E24AA"),
    ("Education", "📚", "#3949AB"),
    ("Shopping", "🛍️", "#FB8C00"),
    ("Bills", "💡", "#FDD835"),
    ("Other", "📦", "#757575"),
)


async def seed_default_categories(session: AsyncSession) -> int:
    """Insert global default categories. Idempotent — returns count of new rows."""
    existing = (
        (await session.execute(select(Category.name).where(Category.household_id.is_(None))))
        .scalars()
        .all()
    )
    existing_set = set(existing)

    inserted = 0
    for name, icon, color in DEFAULT_CATEGORIES:
        if name in existing_set:
            continue
        session.add(Category(name=name, icon=icon, color=color, household_id=None))
        inserted += 1
    await session.flush()
    return inserted


async def list_available_categories(session: AsyncSession, user: User) -> list[Category]:
    """Return the caller's available categories — global defaults + their household's.

    Mirrors ``insights.categorizer.load_available_categories`` scoping: global
    (``household_id IS NULL``) plus the caller's own household, never another
    household's categories.
    """
    from finsight.budgets.service import _resolve_user_household
    from finsight.insights.categorizer import load_available_categories

    await seed_default_categories(session)
    household = await _resolve_user_household(session, user)
    return await load_available_categories(session, household.id)
