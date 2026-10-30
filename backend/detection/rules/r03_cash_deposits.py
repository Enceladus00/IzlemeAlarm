from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from backend.detection.metadata import (
    ParameterSpec,
    RawRuleResult,
    RuleDefinition,
    RuleStrategy,
)
from backend.detection.parameters import R03Values
from backend.models import Customer, Transaction


class CashDepositsRule(RuleStrategy):
    definition = RuleDefinition(
        code="R03",
        name="Çok sayıda nakit yatırma - Aynı hesaba eşik altı nakit yatırma",
        description="Aynı müşteriye ait aynı hesaba gelen eşik altı nakit işlemlerini ayarlanabilir gün penceresinde sayar.",
        steps=(
            "Ayarlı gün penceresinde hesaba gelen nakit işlemleri al (channel).",
            "Tutarı L'nin altında olanları say -> x.",
            "s = sigmoid((x - x_esik) / c).",
        ),
        alert_mode="ALERT",
        parameter_model=R03Values,
        parameters=(
            ParameterSpec("limits", "map[currency, decimal]", "currency", "Cash limit L per customer type and currency.", True),
            ParameterSpec("x_esik", "integer", "transaction count", "Score is 0.5 at this count.", True),
            ParameterSpec("x_kesin", "integer", "transaction count", "Score is 0.9 at this count; must exceed x_esik.", True),
            ParameterSpec("cash_channels", "list[channel]", "channel", "Transaction channels treated as cash deposits; provisional suggestion: atm and branch.", True),
            ParameterSpec("window_days", "integer", "days", "Calendar-day lookback including the run date.", True),
        ),
        analyst_review_notes=(
            "Cash-channel classification is institution-owned; confirm selected channels before approving this rule.",
            "Counts are conservatively kept separate by account and currency, and transfers between the same customer's accounts are excluded. An analyst should confirm whether the intended policy aggregates across a customer's accounts.",
            "Daily deduplication consolidates same-day R03 results into one alert, accumulates evidence, and keeps the highest score. An analyst should confirm whether distinct same-day episodes should instead create separate alerts.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="Required transaction fields exist, but cash-channel classification and account/currency aggregation need analyst approval.",
    )

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: datetime,
    ) -> list[RawRuleResult]:
        window_days_by_customer = {
            customer.customer_id: int(
                parameter_sets[customer.customer_type]["values"].get(
                    "window_days", 7
                )
            )
            for customer in customers
        }
        window_start_by_customer = {
            customer.customer_id: datetime.combine(
                as_of.date()
                - timedelta(days=window_days_by_customer[customer.customer_id] - 1),
                time.min,
            )
            for customer in customers
        }
        customer_by_id = {customer.customer_id: customer for customer in customers}
        grouped: dict[tuple[int, int, str], list[Transaction]] = defaultdict(list)
        ignored_currency_counts: dict[int, int] = defaultdict(int)
        for transaction in transactions:
            receiver_customer_id = transaction.receiver_account.customer_id
            owner = customer_by_id.get(receiver_customer_id)
            if owner is None:
                continue
            if not (
                window_start_by_customer[receiver_customer_id]
                <= transaction.tx_time
                < as_of
            ):
                continue
            if transaction.sender_account.customer_id == receiver_customer_id:
                continue
            parameter_set = parameter_sets.get(owner.customer_type)
            if parameter_set is None:
                continue
            parameter_values = parameter_set["values"]
            if (
                transaction.channel in set(parameter_values["cash_channels"])
                and transaction.currency not in parameter_values["limits"]
            ):
                ignored_currency_counts[owner.customer_id] += 1
            grouped[
                (
                    owner.customer_id,
                    transaction.receiver_account_id,
                    transaction.currency,
                )
            ].append(transaction)

        results: list[RawRuleResult] = []
        for customer in customers:
            parameter_set = parameter_sets[customer.customer_type]
            values = parameter_set["values"]
            cash_channels = set(values["cash_channels"])
            limits = {
                currency: Decimal(str(limit))
                for currency, limit in values["limits"].items()
            }
            candidates: list[
                tuple[Decimal, list[Transaction], int, Decimal, str]
            ] = []
            for (customer_id, account_id, currency), account_transactions in grouped.items():
                if (
                    customer_id != customer.customer_id
                    or currency not in limits
                ):
                    continue
                limit = limits[currency]
                below_limit = [
                    transaction
                    for transaction in account_transactions
                    if transaction.channel in cash_channels and transaction.amount < limit
                ]
                candidates.append(
                    (Decimal(len(below_limit)), below_limit, account_id, limit, currency)
                )

            if candidates:
                selected = max(
                    candidates, key=lambda candidate: (candidate[0], candidate[2])
                )
                raw_x, _, account_id, limit, currency = selected
                evidence = [
                    transaction
                    for candidate in candidates
                    if candidate[0] == raw_x
                    for transaction in candidate[1]
                ]
            else:
                raw_x, evidence, account_id, limit, currency = (
                    Decimal("0"),
                    [],
                    None,
                    None,
                    None,
                )
            trace = [
                {
                    "step": 1,
                    "text": self.definition.steps[0],
                    "status": "completed",
                    "details": {
                        "window_start": window_start_by_customer[
                            customer.customer_id
                        ].isoformat(),
                        "window_days": window_days_by_customer[customer.customer_id],
                        "as_of": as_of.isoformat(),
                        "cash_channels": sorted(cash_channels),
                        "matching_account_count": len(candidates),
                        "unlisted_currency_transaction_count": ignored_currency_counts[
                            customer.customer_id
                        ],
                    },
                },
                {
                    "step": 2,
                    "text": self.definition.steps[1],
                    "status": "completed",
                    "details": {
                        "account_id": account_id,
                        "currency": currency,
                        "limit": str(limit) if limit is not None else None,
                        "x": int(raw_x),
                        "exact_limit_excluded": True,
                    },
                },
                {
                    "step": 3,
                    "text": self.definition.steps[2],
                    "status": "pending_shared_scoring",
                    "details": {},
                },
            ]
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=raw_x,
                    transactions=evidence,
                    step_trace=trace,
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    ignored_currency_count=ignored_currency_counts[customer.customer_id],
                )
            )
        return results
