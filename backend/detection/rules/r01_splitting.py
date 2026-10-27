from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from backend.detection.metadata import (
    ParameterSpec,
    RawRuleResult,
    RuleDefinition,
    RuleStrategy,
)
from backend.detection.parameters import R01Values
from backend.models import Customer, Transaction


class SplittingRule(RuleStrategy):
    definition = RuleDefinition(
        code="R01",
        name="Bölme - Limitin hemen altında birden çok işlem",
        description="Limitin hemen altındaki tekrar eden işlemleri gelir ve üst limitle birlikte değerlendirir.",
        steps=(
            "Son 7 günün işlemlerini al.",
            "Limitin hemen altındaki [0,9*L, L) işlemleri say -> x.",
            "Limitin hemen üstünde işlem varsa veya bant toplamı gelire göre küçükse s = 0.",
            "Değilse s = sigmoid((x - x_esik) / c).",
        ),
        alert_mode="ALERT",
        parameter_model=R01Values,
        parameters=(
            ParameterSpec("limits", "map[currency, decimal]", "currency", "Limit L per customer type and currency.", True),
            ParameterSpec("x_esik", "decimal integer", "transaction count", "Score is 0.5 at this near-limit count.", True),
            ParameterSpec("x_kesin", "decimal integer", "transaction count", "Score is 0.9 at this near-limit count; must exceed x_esik.", True),
            ParameterSpec("minimum_income_ratio", "decimal", "ratio", "Minimum band total divided by monthly income.", True),
            ParameterSpec("income_currency", "ISO currency", "currency", "Currency used for monthly_income; no FX conversion is applied.", True),
        ),
    )

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: datetime,
    ) -> list[RawRuleResult]:
        window_start = as_of - timedelta(days=7)
        grouped: dict[tuple[int, str], list[Transaction]] = defaultdict(list)
        for transaction in transactions:
            if window_start <= transaction.tx_time < as_of:
                grouped[
                    (transaction.sender_account.customer_id, transaction.currency)
                ].append(transaction)

        results: list[RawRuleResult] = []
        for customer in customers:
            parameter_set = parameter_sets[customer.customer_type]
            values = parameter_set["values"]
            limits = {
                currency: Decimal(str(limit))
                for currency, limit in values["limits"].items()
            }
            ignored_currency_count = sum(
                len(group)
                for (customer_id, currency), group in grouped.items()
                if customer_id == customer.customer_id and currency not in limits
            )
            global_limit_hit = any(
                transaction.amount > limits[currency]
                for currency in limits
                for transaction in grouped.get((customer.customer_id, currency), [])
            )
            candidates: list[tuple[Decimal, Decimal, list[Transaction], dict[str, Any]]] = []
            for currency, limit in limits.items():
                currency_transactions = grouped.get((customer.customer_id, currency), [])
                band = [
                    transaction
                    for transaction in currency_transactions
                    if limit * Decimal("0.9") <= transaction.amount < limit
                ]
                raw_x = Decimal(len(band))
                income = customer.monthly_income
                income_currency = values["income_currency"]
                ratio: Decimal | None = None
                if income is not None and income > 0 and currency == income_currency:
                    ratio = sum((transaction.amount for transaction in band), Decimal("0")) / income
                limit_exceeded = global_limit_hit
                income_too_small = ratio is None or ratio < Decimal(
                    str(values["minimum_income_ratio"])
                )
                force_zero = limit_exceeded or income_too_small
                trace = [
                    {
                        "step": 1,
                        "text": self.definition.steps[0],
                        "status": "completed",
                        "details": {
                            "window_start": window_start.isoformat(),
                            "as_of": as_of.isoformat(),
                            "transaction_count": len(currency_transactions),
                            "currency": currency,
                            "unlisted_currency_transaction_count": ignored_currency_count,
                        },
                    },
                    {
                        "step": 2,
                        "text": self.definition.steps[1],
                        "status": "completed",
                        "details": {
                            "limit": str(limit),
                            "band_lower_inclusive": str(limit * Decimal("0.9")),
                            "band_upper_exclusive": str(limit),
                            "x": int(raw_x),
                            "band_total": str(
                                sum((transaction.amount for transaction in band), Decimal("0"))
                            ),
                        },
                    },
                    {
                        "step": 3,
                        "text": self.definition.steps[2],
                        "status": "blocked" if force_zero else "passed",
                        "details": {
                            "limit_exceeded": limit_exceeded,
                            "income_currency": income_currency,
                            "monthly_income_available": income is not None and income > 0,
                            "income_ratio": str(ratio) if ratio is not None else None,
                            "minimum_income_ratio": str(values["minimum_income_ratio"]),
                            "score_forced_to_zero": force_zero,
                        },
                    },
                    {
                        "step": 4,
                        "text": self.definition.steps[3],
                        "status": "pending_shared_scoring",
                        "details": {},
                    },
                ]
                evidence = list(band)
                if limit_exceeded:
                    evidence.extend(
                        transaction
                        for transaction in currency_transactions
                        if transaction.amount > limit
                    )
                candidates.append(
                    (raw_x, limit, evidence, {"trace": trace, "force_zero": force_zero})
                )

            if candidates:
                raw_x, _limit, evidence, selected = max(
                    candidates,
                    key=lambda candidate: (
                        not candidate[3]["force_zero"],
                        candidate[0],
                        candidate[1],
                    ),
                )
                results.append(
                    RawRuleResult(
                        customer_id=customer.customer_id,
                        customer_type=customer.customer_type,
                        raw_x=raw_x,
                        transactions=evidence,
                        step_trace=selected["trace"],
                        x_esik=Decimal(str(values["x_esik"])),
                        x_kesin=Decimal(str(values["x_kesin"])),
                        force_zero=selected["force_zero"],
                        ignored_currency_count=ignored_currency_count,
                    )
                )
            else:
                results.append(
                    RawRuleResult(
                        customer_id=customer.customer_id,
                        customer_type=customer.customer_type,
                        raw_x=Decimal("0"),
                        transactions=[],
                        step_trace=[
                            {
                                "step": index,
                                "text": step,
                                "status": "no_currency_limit",
                                "details": {},
                            }
                            for index, step in enumerate(self.definition.steps, 1)
                        ],
                        x_esik=Decimal(str(values["x_esik"])),
                        x_kesin=Decimal(str(values["x_kesin"])),
                        force_zero=True,
                        ignored_currency_count=ignored_currency_count,
                    )
                )
        return results
