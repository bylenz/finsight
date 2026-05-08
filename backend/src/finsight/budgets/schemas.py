"""Pydantic schemas for budgets and alerts."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

Currency = Literal["PEN", "USD"]
Period = Literal["monthly"]
AlertTypeStr = Literal["80", "100"]


class BudgetCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: Currency
    period: Period = "monthly"
    category_id: int | None = None


class BudgetUpdate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: Currency
    period: Period = "monthly"
    category_id: int | None = None


class BudgetPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    household_id: int
    category_id: int | None
    amount: Decimal
    currency: str
    period: str


class BudgetStatus(BaseModel):
    spent: Decimal
    limit: Decimal
    percentage: float
    currency: str


class AlertPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    budget_id: int
    type: str
    triggered_at: datetime

    @field_serializer("triggered_at")
    def _serialize_triggered_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
