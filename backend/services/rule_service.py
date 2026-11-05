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
                    "analyst_review_notes": list(
                        registry[rule.rule_code].definition.analyst_review_notes
                    ),
                    "feasibility": registry[rule.rule_code].definition.feasibility,
                    "feasibility_reason": registry[
                        rule.rule_code
                    ].definition.feasibility_reason,
                }
                if rule.rule_code in registry
                else None,
            }
            for rule in self._repository.list_rules()
        ]

    def rule_history(self, rule_code: str, limit: int = 50) -> list[dict[str, Any]]:
        """E07 "Değişiklik geçmişi": each save as a list of changed fields
        (old -> new) with who saved it and the stated reason."""
        if self._repository.get_rule(rule_code) is None:
            raise RuleNotFound("Rule not found.")
        return [
            {
                "change_id": row["change_id"],
                "changed_at": row["changed_at"],
                "actor_name": row["actor_name"],
                "actor_role": row["actor_role"],
                "reason": (row["details"].get("reason") or None),
                "changes": _diff_rule_change(row["details"]),
            }
            for row in self._repository.rule_history(rule_code, limit)
        ]

    def update_rule(
        self,
        rule_code: str,
        thresholds: dict[str, Any],
        is_active: bool,
        actor_id: int,
        weight: Decimal | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        rule: MonitoringRule | None = self._repository.get_rule(rule_code)
        if rule is None:
            raise RuleNotFound("Rule not found.")
        normalized_thresholds = validate_thresholds(rule.rule_code, thresholds)
        if is_active and all(
            values["status"] == "UNSET"
            for values in normalized_thresholds.values()
        ):
            raise InvalidRuleThresholds(
                "A rule cannot be activated until at least one customer type is configured."
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
            rule, normalized_thresholds, is_active, normalized_weight, actor_id, reason
        )
        return {
            "rule_code": rule.rule_code,
            "is_active": rule.is_active,
            "weight": rule.weight,
            "thresholds": rule.thresholds,
        }


def _diff_rule_change(details: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten one rule.updated audit record into the fields that changed.

    field is "is_active", "weight", "<TYPE>.status" or "<TYPE>.<parameter>".
    Older records without old_* values only report the threshold changes.
    """
    changes: list[dict[str, Any]] = []
    if "old_is_active" in details and details.get("old_is_active") != details.get("new_is_active"):
        changes.append(
            {"field": "is_active", "old": details.get("old_is_active"), "new": details.get("new_is_active")}
        )
    if "old_weight" in details and _same_number(details.get("old_weight"), details.get("new_weight")) is False:
        changes.append({"field": "weight", "old": details.get("old_weight"), "new": details.get("new_weight")})
    old = details.get("old_thresholds") or {}
    new = details.get("new_thresholds") or {}
    for customer_type in sorted(set(old) | set(new)):
        old_set = old.get(customer_type) or {}
        new_set = new.get(customer_type) or {}
        if old_set.get("status") != new_set.get("status"):
            changes.append(
                {"field": f"{customer_type}.status", "old": old_set.get("status"), "new": new_set.get("status")}
            )
        old_values = old_set.get("values") or {}
        new_values = new_set.get("values") or {}
        for name in sorted(set(old_values) | set(new_values)):
            if old_values.get(name) != new_values.get(name):
                changes.append(
                    {"field": f"{customer_type}.{name}", "old": old_values.get(name), "new": new_values.get(name)}
                )
    return changes


def _same_number(left: Any, right: Any) -> bool | None:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (ArithmeticError, ValueError):
        return left == right
