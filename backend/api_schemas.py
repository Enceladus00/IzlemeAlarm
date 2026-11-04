from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RuleUpdate(BaseModel):
    is_active: bool
    thresholds: dict[str, Any]
    weight: Decimal | None = Field(default=None, ge=0, le=1)
    # K5: every rule change needs a reason (written to the audit log).
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A change reason is required.")
        return value.strip()

    @field_validator("weight", mode="before")
    @classmethod
    def reject_boolean_weight(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Rule weight must be numeric.")
        return value


AlertStatus = Literal["new", "in_review", "closed", "confirmed_suspicious"]


class AlertStatusUpdate(BaseModel):
    status: AlertStatus
    note: str | None = Field(default=None, max_length=2000)


class AlertDecisionRequest(BaseModel):
    alert_ids: list[int] = Field(min_length=1, max_length=50)
    status: AlertStatus
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("alert_ids")
    @classmethod
    def reject_duplicate_ids(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("Alert IDs must be unique.")
        return value

    @field_validator("note")
    @classmethod
    def reject_blank_note(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A note is required for every alert decision.")
        return value


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)
    role_code: str = Field(min_length=1, max_length=20)


class UserUpdate(BaseModel):
    role_code: str | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None


class TransactionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    transaction_no: str
    amount: Decimal
    currency: str
    tx_time: datetime
    country_code: str
    channel: str


class AlertView(BaseModel):
    alert_id: int
    rule_code: str
    rule_name: str
    customer_no: str
    customer_name: str
    severity: str
    score: Decimal | None
    status: str
    created_at: datetime
    transaction_count: int


class AlertDetail(AlertView):
    transactions: list[TransactionView]
    history: list[dict[str, Any]]
