from decimal import Decimal
from typing import Any

from backend.models import MonitoringRule
from backend.detection.parameters import validate_rule_parameters
from backend.detection.registry import load_rule_registry
from backend.repositories.rule_repository import SqlAlchemyRuleRepository


class RuleNotFound(LookupError):
    pass


class InvalidRuleThresholds(ValueError):
    pass


def validate_thresholds(rule_code: str, values: dict[str, Any]) -> dict[str, Any]:
    try:
        strategy = load_rule_registry().get(rule_code)
        if strategy is None:
            raise ValueError("No implementation is registered for this rule.")
        return validate_rule_parameters(
            rule_code, strategy.definition.parameter_model, values
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidRuleThresholds(
            f"Invalid {rule_code} parameter values: {exc}"
        ) from exc


class RuleService:
    def __init__(self, repository: SqlAlchemyRuleRepository) -> None:
        self._repository = repository

    def list_rules(self) -> list[dict[str, Any]]:
        registry = load_rule_registry()
        return [
            {
                "rule_code": rule.rule_code,
                "name": registry[rule.rule_code].definition.name
                if rule.rule_code in registry
                else rule.name,
                "description": registry[rule.rule_code].definition.description
                if rule.rule_code in registry
                else rule.description,
                "is_active": rule.is_active,
                "weight": rule.weight,
                "thresholds": rule.thresholds,
                "metadata": {
                    "steps": list(registry[rule.rule_code].definition.steps),
                    "alert_mode": registry[rule.rule_code].definition.alert_mode,
                    "parameters": [
                        {
                            "name": item.name,
                            "type": item.type,
                            "unit": item.unit,
                            "meaning": item.meaning,
                            "required": item.required,
                        }
                        for item in registry[rule.rule_code].definition.parameters
                    ],
                }
                if rule.rule_code in registry
                else None,
            }
            for rule in self._repository.list_rules()
        ]

    def update_rule(
        self,
        rule_code: str,
        thresholds: dict[str, Any],
        is_active: bool,
        actor_id: int,
        weight: Decimal | None = None,
    ) -> dict[str, Any]:
        rule: MonitoringRule | None = self._repository.get_rule(rule_code)
        if rule is None:
            raise RuleNotFound("Rule not found.")
        normalized_thresholds = validate_thresholds(rule.rule_code, thresholds)
        if is_active and any(
            values["status"] == "UNSET"
            for values in normalized_thresholds.values()
        ):
            raise InvalidRuleThresholds(
                "A rule cannot be activated while any customer type is UNSET."
            )
        try:
            normalized_weight = (
                rule.weight if weight is None else Decimal(str(weight))
            )
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise InvalidRuleThresholds("Rule weight must be between 0 and 1.") from exc
        if (
            not normalized_weight.is_finite()
            or normalized_weight < 0
            or normalized_weight > 1
        ):
            raise InvalidRuleThresholds("Rule weight must be between 0 and 1.")
        self._repository.save_rule(
            rule, normalized_thresholds, is_active, normalized_weight, actor_id
        )
        return {
            "rule_code": rule.rule_code,
            "is_active": rule.is_active,
            "weight": rule.weight,
            "thresholds": rule.thresholds,
        }
