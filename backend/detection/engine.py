import logging
from datetime import datetime
from decimal import Decimal
from time import perf_counter
from typing import Any

from backend.detection.evaluation import DetectionEvaluation
from backend.detection.metadata import DetectionContext, RuleResultEvidence
from backend.detection.parameters import (
    CUSTOMER_TYPES,
    parameter_set_for,
    validate_rule_parameters,
)
from backend.detection.registry import load_rule_registry
from backend.detection.scoring import calculate_score
from backend.models import Customer, MonitoringRule, Transaction


logger = logging.getLogger(__name__)


class DetectionEngine:
    def evaluate(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        rules_by_code: dict[str, MonitoringRule],
        *,
        as_of: datetime,
        rule_overrides: dict[str, dict[str, Any]] | None = None,
        context: DetectionContext | None = None,
    ) -> DetectionEvaluation:
        registry = load_rule_registry()
        overrides = rule_overrides or {}
        database_codes = set(rules_by_code)
        unknown_overrides = set(overrides) - database_codes
        if unknown_overrides:
            raise RuntimeError(
                f"Detection parameter overrides have no database rows: {sorted(unknown_overrides)}"
            )
        active_rules = {
            code: rule for code, rule in rules_by_code.items() if rule.is_active
        }
        active_rules.update(
            (code, rules_by_code[code])
            for code in overrides
            if code in rules_by_code
        )
        missing_implementations = set(active_rules) - set(registry)
        missing_rows = set(registry) - database_codes
        if missing_implementations or missing_rows:
            raise RuntimeError(
                "Detection registry mismatch: "
                f"active_rules_without_implementation={sorted(missing_implementations)}, "
                f"implementations_without_database_row={sorted(missing_rows)}"
            )

        results: list[RuleResultEvidence] = []
        summary: dict[str, object] = {
            "as_of": as_of.isoformat(),
            "customer_count": len(customers),
            "transaction_count": len(transactions),
            "rule_count": len(active_rules),
            "demo_only": bool(overrides),
            "unknown_customer_type_count": sum(
                customer.customer_type not in CUSTOMER_TYPES for customer in customers
            ),
            "rules": {},
        }
        rule_summaries: dict[str, dict[str, object]] = {}

        for rule_code in sorted(active_rules):
            rule_started = perf_counter()
            rule = active_rules[rule_code]
            strategy = registry[rule_code]
            definition = strategy.definition
            rule_thresholds = overrides.get(rule_code, rule.thresholds)
            validated = validate_rule_parameters(
                rule_code, definition.parameter_model, rule_thresholds
            )
            rule_summary: dict[str, object] = {
                "evaluated": 0,
                "alerts": 0,
                "signals": 0,
                "ignored_currency_transaction_count": 0,
                "skipped_unset": {},
                "skipped_customer_type": 0,
                "provisional_customer_types": [],
            }
            rule_summaries[rule_code] = rule_summary

            known_customers: dict[str, list[Customer]] = {
                customer_type: [
                    customer
                    for customer in customers
                    if customer.customer_type == customer_type
                ]
                for customer_type in CUSTOMER_TYPES
            }
            unknown_customers = [
                customer
                for customer in customers
                if customer.customer_type not in CUSTOMER_TYPES
            ]
            for customer in unknown_customers:
                results.append(
                    RuleResultEvidence(
                        rule_code=rule_code,
                        customer_id=customer.customer_id,
                        customer_type=customer.customer_type,
                        parameter_snapshot={},
                        parameter_status="UNSET",
                        result_status="skipped_customer_type",
                        raw_x=None,
                        score=None,
                        step_trace=[
                            {
                                "step": index,
                                "text": text,
                                "status": "skipped_customer_type",
                                "details": {},
                            }
                            for index, text in enumerate(definition.steps, 1)
                        ],
                        transactions=[],
                        alert_mode=definition.alert_mode,
                    )
                )
                rule_summary["skipped_customer_type"] = (
                    int(rule_summary["skipped_customer_type"]) + 1
                )

            for customer_type, type_customers in known_customers.items():
                if not type_customers:
                    continue
                parameter_set = parameter_set_for(validated, customer_type)
                assert parameter_set is not None
                status = parameter_set["status"]
                if status == "UNSET":
                    logger.warning(
                        "Detection rule skipped: rule_code=%s customer_type=%s status=UNSET customers=%d",
                        rule_code,
                        customer_type,
                        len(type_customers),
                    )
                    rule_summary["skipped_unset"][customer_type] = len(type_customers)
                    results.extend(
                        RuleResultEvidence(
                            rule_code=rule_code,
                            customer_id=customer.customer_id,
                            customer_type=customer_type,
                            parameter_snapshot=parameter_set,
                            parameter_status=status,
                            result_status="skipped_unset",
                            raw_x=None,
                            score=None,
                            step_trace=[
                                {
                                    "step": index,
                                    "text": text,
                                    "status": "skipped_unset",
                                    "details": {"parameter_status": status},
                                }
                                for index, text in enumerate(definition.steps, 1)
                            ],
                            transactions=[],
                            alert_mode=definition.alert_mode,
                        )
                        for customer in type_customers
                    )
                    continue
                if status == "PROVISIONAL":
                    logger.warning(
                        "Detection rule uses PROVISIONAL parameters: rule_code=%s customer_type=%s customers=%d",
                        rule_code,
                        customer_type,
                        len(type_customers),
                    )
                    provisional_types = rule_summary["provisional_customer_types"]
                    assert isinstance(provisional_types, list)
                    provisional_types.append(customer_type)

                if rule_code == "R15":
                    raw_results = strategy.evaluate_raw(
                        type_customers,
                        transactions,
                        {customer_type: parameter_set},
                        as_of=as_of,
                        context=context,
                    )
                else:
                    raw_results = strategy.evaluate_raw(
                        type_customers,
                        transactions,
                        {customer_type: parameter_set},
                        as_of=as_of,
                    )
                raw_by_customer = {item.customer_id: item for item in raw_results}
                expected_ids = {customer.customer_id for customer in type_customers}
                if set(raw_by_customer) != expected_ids or len(raw_results) != len(raw_by_customer):
                    raise RuntimeError(
                        f"Rule {rule_code} must return exactly one result per customer type set."
                    )
                for customer in type_customers:
                    raw = raw_by_customer[customer.customer_id]
                    if raw.score_override is not None:
                        score = raw.score_override
                    elif raw.x_esik is not None or raw.binary_limit is not None:
                        score = calculate_score(
                            raw.raw_x,
                            x_esik=raw.x_esik,
                            x_kesin=raw.x_kesin,
                            binary_limit=raw.binary_limit,
                            force_zero=raw.force_zero,
                        )
                    else:
                        score = Decimal("0")
                    trace = [dict(step) for step in raw.step_trace]
                    for step in trace:
                        if step["status"] == "pending_shared_scoring":
                            step["status"] = "completed"
                            step["details"] = {
                                **step["details"],
                                "score": str(score),
                            }
                    if trace and not any(
                        step["status"] == "completed"
                        and "score" in step["details"]
                        for step in trace
                    ):
                        trace[-1]["details"] = {
                            **trace[-1]["details"],
                            "score": str(score),
                        }
                    results.append(
                        RuleResultEvidence(
                            rule_code=rule_code,
                            customer_id=customer.customer_id,
                            customer_type=customer_type,
                            parameter_snapshot=parameter_set,
                            parameter_status=status,
                            result_status="evaluated",
                            raw_x=raw.raw_x,
                            score=score,
                            step_trace=trace,
                            transactions=raw.transactions,
                            alert_mode=definition.alert_mode,
                        )
                    )
                    rule_summary["evaluated"] = int(rule_summary["evaluated"]) + 1
                    rule_summary["ignored_currency_transaction_count"] = (
                        int(rule_summary["ignored_currency_transaction_count"])
                        + raw.ignored_currency_count
                    )
                    if definition.alert_mode == "SIGNAL_ONLY" and score > 0:
                        rule_summary["signals"] = int(rule_summary["signals"]) + 1
                    elif score >= Decimal("0.5"):
                        rule_summary["alerts"] = int(rule_summary["alerts"]) + 1
            rule_summary["elapsed_ms"] = round(
                (perf_counter() - rule_started) * 1000, 3
            )

        summary["rules"] = rule_summaries
        return DetectionEvaluation(results=results, summary=summary)
