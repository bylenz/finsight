from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
