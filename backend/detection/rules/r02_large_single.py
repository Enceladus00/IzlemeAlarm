from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.detection.metadata import (
    ParameterSpec,
    RawRuleResult,
    RuleDefinition,
    RuleStrategy,
)
from backend.detection.parameters import R02Values
from backend.models import Customer, Transaction


class LargeSingleTransactionRule(RuleStrategy):
    definition = RuleDefinition(
        code="R02",
        name="Büyük tek işlem - Limiti aşan işlem (büyüklük sinyali)",
        description="Müşteri tipi ve para birimi limitini aşan tek işlemi INFO sinyali olarak kaydeder.",
        steps=(
            "Müşteri tipine ve para birimine göre limiti L seç.",
            "Tutar >= L ise s = 1, değilse s = 0.",
            "INFO olarak kaydet, skoru birleşik riske gönder.",
        ),
        alert_mode="SIGNAL_ONLY",
        parameter_model=R02Values,
        parameters=(
            ParameterSpec("limits", "map[currency, decimal]", "currency", "Limit L per customer type and currency.", True),
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
        grouped: dict[int, list[Transaction]] = defaultdict(list)
        for transaction in transactions:
            if transaction.tx_time >= as_of:
                continue
            customer_ids = {
                transaction.sender_account.customer_id,
                transaction.receiver_account.customer_id,
            }
            for customer_id in customer_ids:
                grouped[customer_id].append(transaction)

        results: list[RawRuleResult] = []
        for customer in customers:
            parameter_set = parameter_sets[customer.customer_type]
            values = parameter_set["values"]
            limits = {
                currency: Decimal(str(limit))
                for currency, limit in values["limits"].items()
            }
            qualifying = [
                (transaction, limits[transaction.currency])
                for transaction in grouped.get(customer.customer_id, [])
                if transaction.currency in limits
            ]
            ignored_currency_count = sum(
                transaction.currency not in limits
                for transaction in grouped.get(customer.customer_id, [])
            )
            selected = max(
                qualifying,
                key=lambda pair: (pair[0].amount / pair[1], pair[0].amount),
                default=None,
            )
            raw_x = selected[0].amount if selected else Decimal("0")
            limit = selected[1] if selected else None
            evidence = [selected[0]] if selected and selected[0].amount >= limit else []
            trace = [
                {
                    "step": 1,
                    "text": self.definition.steps[0],
                    "status": "completed",
                    "details": {
                        "currency_limits": {
                            currency: str(value) for currency, value in limits.items()
                        },
                        "transactions_considered": len(qualifying),
                        "unlisted_currency_transaction_count": ignored_currency_count,
                    },
                },
                {
                    "step": 2,
                    "text": self.definition.steps[1],
                    "status": "completed",
                    "details": {
                        "amount": str(raw_x),
                        "limit": str(limit) if limit is not None else None,
                        "threshold_met": bool(limit is not None and raw_x >= limit),
                    },
                },
                {
                    "step": 3,
                    "text": self.definition.steps[2],
                    "status": "completed",
                    "details": {"alert_mode": self.definition.alert_mode},
                },
            ]
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=raw_x,
                    transactions=evidence,
                    step_trace=trace,
                    binary_limit=limit,
                    ignored_currency_count=ignored_currency_count,
                )
            )
        return results
