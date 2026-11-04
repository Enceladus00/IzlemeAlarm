from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from backend.detection.parameters import RuleParameterValues
from backend.models import Customer, Transaction


# SEVERITY_RAISE: R17 opens no alert; it raises the severity of open alerts.
AlertMode = Literal["ALERT", "SIGNAL_ONLY", "SEVERITY_RAISE"]
RuleFeasibility = Literal["HIGH", "MEDIUM", "LOW"]


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
    analyst_review_notes: tuple[str, ...] = ()
    feasibility: RuleFeasibility = "HIGH"
    feasibility_reason: str = ""
    # Evaluation order: 0 = transaction rules, 1 = combines the run's scores (R18),
    # 2 = works on persisted alerts after the run is saved (R17).
    stage: int = 0


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
    score_override: Decimal | None = None


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
    # Score needed to open an alert; None means the common 0.5 (R18 sets its own).
    alert_threshold: Decimal | None = None


@dataclass(frozen=True)
class DetectionContext:
    suspicious_customer_ids_by_status: dict[str, set[int]]
    suspicious_account_ids_by_status: dict[str, set[int]]


class RuleStrategy:
    definition: RuleDefinition

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: Any,
        context: DetectionContext | None = None,
    ) -> list[RawRuleResult]:
        raise NotImplementedError

    def evaluate_combined(
        self,
        customers: list[Customer],
        parameter_sets: dict[str, dict[str, Any]],
        prior_results: list["RuleResultEvidence"],
        weights: dict[str, Decimal],
        *,
        as_of: Any,
    ) -> list[RawRuleResult]:
        """Stage-1 rules: build a result from the same run's other results."""
        raise NotImplementedError
