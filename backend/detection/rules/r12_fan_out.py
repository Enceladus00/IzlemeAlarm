from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from statistics import pstdev
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R12Values
from backend.detection.rules.common import calendar_window_start
from backend.models import Customer, Transaction


class FanOutRule(RuleStrategy):
    definition = RuleDefinition(
        code="R12",
        name="Dağıtma (fan-out)",
        description="Çok sayıda yeni alıcıya yapılan çıkışları bulur ve benzer tutarlara ek ağırlık verir.",
        steps=(
            "Dışarı giden işlemleri ayarlı takvim-günü penceresinde seç.",
            "Nakit hesaplarını ve müşterinin kendi hesaplarını dışla; yeni alıcıları bul.",
            "Yeni alıcı sayısını, eşit tutar değişkenlik katsayısına göre ayarla.",
            "Ayarlı sayımı sigmoid ile puanla.",
        ),
        alert_mode="ALERT",
        parameter_model=R12Values,
        parameters=(
            ParameterSpec("window_days", "integer", "days", "Calendar-day lookback including run date.", True),
            ParameterSpec("cash_accounts", "account ID list", "account_id", "Recipient accounts excluded as cash/custody accounts.", False),
            ParameterSpec("cv_threshold", "decimal", "coefficient of variation", "Below this, similar amounts increase the count signal.", True),
            ParameterSpec("cv_multiplier", "decimal", "multiplier", "Multiplier applied to new-recipient count when CV is below threshold.", True),
            ParameterSpec("x_esik", "decimal", "weighted recipient count", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "decimal", "weighted recipient count", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "New-recipient counts and coefficient of variation are calculated separately by currency to avoid mixing amounts without FX conversion.",
            "The specification calls for population standard deviation (ddof=0), implemented with the Python standard library.",
            "An absent historical transfer is treated as a first contact; validate transaction-history coverage to avoid classifying old recipients as new.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="Uses transaction counterpart accounts and historical first-contact dates; currency-separated variation is implementable without FX.",
    )

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: datetime,
    ) -> list[RawRuleResult]:
        results = []
        for customer in customers:
            values = parameter_sets[customer.customer_type]["values"]
            account_ids = {account.account_id for account in customer.accounts if account.is_active}
            window_start = calendar_window_start(as_of, int(values["window_days"]))
            cash_accounts = set(values["cash_accounts"])
            outgoing = [
                tx
                for tx in transactions
                if window_start <= tx.tx_time < as_of
                and tx.sender_account_id in account_ids
                and tx.receiver_account_id not in cash_accounts
                and tx.receiver_account.customer_id != customer.customer_id
            ]
            first_to_recipient: dict[tuple[int, str], datetime] = {}
            for tx in transactions:
                if (
                    tx.tx_time < as_of
                    and
                    tx.sender_account_id in account_ids
                    and tx.receiver_account_id not in cash_accounts
                    and tx.sender_account.customer_id != tx.receiver_account.customer_id
                ):
                    key = (tx.receiver_account_id, tx.currency)
                    first_to_recipient[key] = min(
                        first_to_recipient.get(key, tx.tx_time),
                        tx.tx_time,
                    )
            new_outgoing = [
                tx
                for tx in outgoing
                if first_to_recipient.get(
                    (tx.receiver_account_id, tx.currency), as_of
                ) >= window_start
            ]
            by_currency: dict[str, dict[int, Decimal]] = defaultdict(
                lambda: defaultdict(Decimal)
            )
            recipient_txs: dict[tuple[str, int], list[Transaction]] = defaultdict(list)
            for tx in new_outgoing:
                by_currency[tx.currency][tx.receiver_account_id] += tx.amount
                recipient_txs[(tx.currency, tx.receiver_account_id)].append(tx)

            best_x = Decimal("0")
            evidence: list[Transaction] = []
            details: dict[str, Any] = {}
            for currency, totals in by_currency.items():
                amounts = [float(amount) for amount in totals.values()]
                n = len(amounts)
                if n == 0:
                    continue
                cv = pstdev(amounts) / (sum(amounts) / n) if n >= 2 else None
                x = Decimal(n)
                if cv is not None and cv < float(values["cv_threshold"]):
                    x *= Decimal(str(values["cv_multiplier"]))
                if x > best_x:
                    best_x = x
                    evidence = [
                        tx
                        for receiver_id in totals
                        for tx in recipient_txs[(currency, receiver_id)]
                    ]
                    details = {
                        "currency": currency,
                        "new_recipient_count": n,
                        "recipient_amount_totals": {
                            str(account_id): str(amount)
                            for account_id, amount in totals.items()
                        },
                        "coefficient_of_variation": cv,
                        "cv_threshold": str(values["cv_threshold"]),
                        "cv_multiplier": str(values["cv_multiplier"]),
                        "x": str(x),
                    }
            suppress = best_x == 0
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=best_x,
                    transactions=evidence,
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "window_start": window_start.isoformat(),
                            "outgoing_count": len(outgoing),
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "new_recipient_transaction_count": len(new_outgoing),
                            "cash_accounts": sorted(cash_accounts),
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": "completed", "details": details},
                        {"step": 4, "text": self.definition.steps[3], "status": (
                            "blocked" if suppress else "pending_shared_scoring"
                        ), "details": {"score_forced_to_zero": suppress}},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=suppress,
                )
            )
        return results
