"""category_cache: LLM categorization cache

Revision ID: 0003_category_cache
Revises: 0002_data_model
Create Date: 2026-05-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_category_cache"
down_revision: str | None = "0002_data_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "category_cache",
        sa.Column("normalized_description", sa.String(length=255), primary_key=True),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_category_cache_category_id", "category_cache", ["category_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_category_cache_category_id", table_name="category_cache")
    op.drop_table("category_cache")
