from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from backend.detection.parameters import RuleParameterValues
from backend.models import Customer, Transaction


AlertMode = Literal["ALERT", "SIGNAL_ONLY"]


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    type: str
    unit: str
    meaning: str
    required: bool


@dataclass(frozen=True)
class RuleDefinition:
    code: str
    name: str
    description: str
    steps: tuple[str, ...]
    alert_mode: AlertMode
    parameter_model: type[RuleParameterValues]
    parameters: tuple[ParameterSpec, ...]


@dataclass(frozen=True)
class RawRuleResult:
    customer_id: int
    customer_type: str | None
    raw_x: Decimal
    transactions: list[Transaction]
    step_trace: list[dict[str, Any]]
    x_esik: Decimal | None = None
    x_kesin: Decimal | None = None
    binary_limit: Decimal | None = None
    force_zero: bool = False
    ignored_currency_count: int = 0


@dataclass(frozen=True)
class RuleResultEvidence:
    rule_code: str
    customer_id: int
    customer_type: str | None
    parameter_snapshot: dict[str, Any]
    parameter_status: str
    result_status: str
    raw_x: Decimal | None
    score: Decimal | None
    step_trace: list[dict[str, Any]]
    transactions: list[Transaction]
    alert_mode: AlertMode


class RuleStrategy:
    definition: RuleDefinition

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: Any,
    ) -> list[RawRuleResult]:
        raise NotImplementedError
