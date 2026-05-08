from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

Currency = Literal["PEN", "USD"]
Source = Literal["manual", "voice", "csv"]


class ExpenseCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: Currency
    description: str | None = Field(default=None, max_length=255)
    category_id: int | None = None
    occurred_at: datetime | None = None
    source: Source | None = None
    is_business: bool = False


class ExpenseUpdate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: Currency
    description: str | None = Field(default=None, max_length=255)
    category_id: int | None = None
    occurred_at: datetime | None = None
    source: Source | None = None
    is_business: bool = False


class ExpensePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    household_id: int
    amount: Decimal
    currency: str
    amount_base: Decimal
    category_id: int | None
    description: str | None
    occurred_at: datetime
    is_business: bool
    source: str

    @field_serializer("occurred_at")
    def _serialize_occurred_at(self, value: datetime) -> str:
        # SQLite returns naive datetimes; assume UTC for consistent ISO-8601 output.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()


class ExpenseListResponse(BaseModel):
    items: list[ExpensePublic]
    limit: int
    offset: int
    total: int
