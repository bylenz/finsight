"""data model: households, household_members, categories, expenses, budgets, alerts

Revision ID: 0002_data_model
Revises: 0001_auth
Create Date: 2026-05-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_data_model"
down_revision: str | None = "0001_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_households_owner_id", "households", ["owner_id"])

    op.create_table(
        "household_members",
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'contributor', 'viewer')",
            name="ck_household_members_role",
        ),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=False),
        sa.Column("color", sa.String(length=9), nullable=False),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_categories_household_id", "categories", ["household_id"])

    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_base", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_business", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "source", sa.String(length=16), nullable=False, server_default="manual"
        ),
        sa.CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        sa.CheckConstraint("currency IN ('PEN', 'USD')", name="ck_expenses_currency"),
        sa.CheckConstraint(
            "source IN ('manual', 'voice', 'csv')", name="ck_expenses_source"
        ),
    )
    op.create_index(
        "ix_expenses_user_occurred_at", "expenses", ["user_id", "occurred_at"]
    )
    op.create_index(
        "ix_expenses_household_occurred_at",
        "expenses",
        ["household_id", "occurred_at"],
    )

    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "period", sa.String(length=16), nullable=False, server_default="monthly"
        ),
        sa.CheckConstraint("amount > 0", name="ck_budgets_amount_positive"),
        sa.CheckConstraint("currency IN ('PEN', 'USD')", name="ck_budgets_currency"),
        sa.CheckConstraint("period IN ('monthly')", name="ck_budgets_period"),
    )
    op.create_index("ix_budgets_household_id", "budgets", ["household_id"])
    op.create_index("ix_budgets_category_id", "budgets", ["category_id"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "budget_id",
            sa.Integer(),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=8), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("type IN ('80', '100')", name="ck_alerts_type"),
    )
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])
    op.create_index("ix_alerts_budget_id", "alerts", ["budget_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_budget_id", table_name="alerts")
    op.drop_index("ix_alerts_user_id", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_budgets_category_id", table_name="budgets")
    op.drop_index("ix_budgets_household_id", table_name="budgets")
    op.drop_table("budgets")

    op.drop_index("ix_expenses_household_occurred_at", table_name="expenses")
    op.drop_index("ix_expenses_user_occurred_at", table_name="expenses")
    op.drop_table("expenses")

    op.drop_index("ix_categories_household_id", table_name="categories")
    op.drop_table("categories")

    op.drop_table("household_members")

    op.drop_index("ix_households_owner_id", table_name="households")
    op.drop_table("households")
