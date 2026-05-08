"""Pydantic schemas for the monthly dashboard aggregate (FR-DASH-01..03)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CategoryBreakdown(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    category_name: str
    amount: Decimal
    percentage: float


class WeekBreakdown(BaseModel):
    week_start: date
    week_end: date
    amount: Decimal


class BudgetSummary(BaseModel):
    budget_id: int
    category_id: int | None
    category_name: str | None
    limit: Decimal
    spent: Decimal
    percentage: float


class DashboardResponse(BaseModel):
    month: str
    currency: str
    total_spent: Decimal
    expense_count: int
    by_category: list[CategoryBreakdown]
    by_week: list[WeekBreakdown]
    budgets: list[BudgetSummary]
