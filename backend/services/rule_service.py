import re
from decimal import Decimal
from typing import Any

from backend.models import MonitoringRule
from backend.repositories.rule_repository import SqlAlchemyRuleRepository


class RuleNotFound(LookupError):
    pass


class InvalidRuleThresholds(ValueError):
    pass


def validate_thresholds(rule_code: str, values: dict[str, Any]) -> dict[str, Any]:
    schemas: dict[str, set[str]] = {
        "R1": {"amount_limit", "proximity_percent", "transaction_count", "window_minutes"},
        "R2": {"outflow_ratio", "window_minutes"},
        "R3": {"average_multiplier", "minimum_history_count"},
        "R4": {"countries", "enabled"},
    }
    if rule_code not in schemas or set(values) != schemas[rule_code]:
        raise InvalidRuleThresholds("Invalid rule threshold fields.")

    def decimal_value(name: str) -> Decimal:
        result = Decimal(str(values[name]))
        if not result.is_finite():
            raise ValueError
        return result

    def integer_value(name: str) -> int:
        result = decimal_value(name)
        if result != result.to_integral_value():
            raise ValueError
        return int(result)

    try:
        if rule_code == "R1":
            if not (0 < decimal_value("proximity_percent") < 100):
                raise ValueError
            if decimal_value("amount_limit") <= 0:
                raise ValueError
            if integer_value("transaction_count") < 2 or integer_value("window_minutes") < 1:
                raise ValueError
        elif rule_code == "R2":
            if not (0 < decimal_value("outflow_ratio") <= 1):
                raise ValueError
            if integer_value("window_minutes") < 1:
                raise ValueError
        elif rule_code == "R3":
            if decimal_value("average_multiplier") <= 0:
                raise ValueError
            if integer_value("minimum_history_count") < 1:
                raise ValueError
        else:
            if not isinstance(values["enabled"], bool):
                raise ValueError
            if not isinstance(values["countries"], list) or any(
                not isinstance(country, str)
                or not re.fullmatch(r"[A-Z]{2}", country)
                for country in values["countries"]
            ):
                raise ValueError
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidRuleThresholds("Threshold values are out of range.") from exc
    return values


class RuleService:
    def __init__(self, repository: SqlAlchemyRuleRepository) -> None:
        self._repository = repository

    def list_rules(self) -> list[dict[str, Any]]:
        return [
            {
                "rule_code": rule.rule_code,
                "name": rule.name,
                "description": rule.description,
                "is_active": rule.is_active,
                "thresholds": rule.thresholds,
            }
            for rule in self._repository.list_rules()
        ]

    def update_rule(
        self,
        rule_code: str,
        thresholds: dict[str, Any],
        is_active: bool,
    ) -> dict[str, Any]:
        rule: MonitoringRule | None = self._repository.get_rule(rule_code)
        if rule is None:
            raise RuleNotFound("Rule not found.")
        normalized_thresholds = validate_thresholds(rule.rule_code, thresholds)
        self._repository.save_rule(rule, normalized_thresholds, is_active)
        return {
            "rule_code": rule.rule_code,
            "is_active": rule.is_active,
            "thresholds": rule.thresholds,
        }
