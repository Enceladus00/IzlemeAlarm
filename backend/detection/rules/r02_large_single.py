from collections import defaultdict
from datetime import datetime, time
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
        name="Büyük tek işlem - Limiti aşan işlem",
        description="Müşteri tipi ve para birimi limitini aşan işlemleri analist uyarısı olarak kaydeder.",
        steps=(
            "Müşteri tipine ve para birimine göre limiti L seç.",
            "Tutar >= L ise s = 1, değilse s = 0.",
            "Eşik üstü işlemleri kanıt olarak bağla ve analist uyarısı oluştur.",
        ),
        alert_mode="ALERT",
        parameter_model=R02Values,
        parameters=(
            ParameterSpec("limits", "map[currency, decimal]", "currency", "Limit L per customer type and currency.", True),
        ),
        analyst_review_notes=(
            "The limit is institution-owned and should remain PROVISIONAL until an analyst approves it. A qualifying amount now creates an analyst alert; review the operational impact after deployment.",
            "Daily deduplication consolidates same-day R02 results into one alert, accumulates evidence, and keeps the highest score. An analyst should confirm whether distinct same-day episodes should instead create separate alerts.",
        ),
        feasibility="HIGH",
        feasibility_reason="Uses available transaction, account-ownership, currency, and customer-type fields with a directly configurable amount limit.",
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
        day_start = datetime.combine(as_of.date(), time.min)
        for transaction in transactions:
            if not day_start <= transaction.tx_time < as_of:
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
            evidence = [
                transaction
                for transaction, transaction_limit in qualifying
                if transaction.amount >= transaction_limit
            ]
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
                        "run_date": as_of.date().isoformat(),
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
                        "qualifying_transaction_count": len(evidence),
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
