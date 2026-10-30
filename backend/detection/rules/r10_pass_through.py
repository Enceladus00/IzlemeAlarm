from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R10Values
from backend.models import Customer, Transaction


class PassThroughRule(RuleStrategy):
    definition = RuleDefinition(
        code="R10",
        name="Geçiş hesabı",
        description="Kısa pencerede gelen hacmin yüksek oranını yeni alıcılara aktaran müşterileri arar.",
        steps=(
            "Son saat penceresindeki dış işlemleri nakit hesapları hariç tutarak seç.",
            "Gelen ve giden hacimleri para birimi bazında hesapla; alt sınırları doğrula.",
            "Pencere içinde ilk kez ödeme yapılan alıcılara giden tutar oranını puanla.",
        ),
        alert_mode="ALERT",
        parameter_model=R10Values,
        parameters=(
            ParameterSpec("window_hours", "integer", "hours", "Lookback ending at the evaluation timestamp.", True),
            ParameterSpec("limits", "map[currency, decimal]", "currency", "Minimum incoming amount by currency.", True),
            ParameterSpec("ratio_low", "decimal", "ratio", "Inclusive minimum outgoing/incoming ratio.", True),
            ParameterSpec("ratio_high", "decimal", "ratio", "Inclusive maximum outgoing/incoming ratio.", True),
            ParameterSpec("cash_accounts", "account ID list", "account_id", "Accounts to exclude from counterpart activity.", False),
            ParameterSpec("x_esik", "decimal", "new-recipient share", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "decimal", "new-recipient share", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "The specification says the lookback ends at run-date end; this implementation ends at the actual evaluation timestamp to avoid using future-dated same-day transactions.",
            "Activity and ratios are evaluated separately by currency; no FX conversion is applied.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="Requires reliable transaction history and counterpart-account classification; both are represented in current data/configuration.",
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
            window_start = as_of - timedelta(hours=int(values["window_hours"]))
            cash_ids = set(values["cash_accounts"])
            relevant = []
            for tx in transactions:
                if not window_start <= tx.tx_time < as_of:
                    continue
                sender_customer = tx.sender_account.customer_id
                receiver_customer = tx.receiver_account.customer_id
                if sender_customer == receiver_customer:
                    continue
                if tx.sender_account_id in cash_ids or tx.receiver_account_id in cash_ids:
                    continue
                if tx.sender_account_id in account_ids or tx.receiver_account_id in account_ids:
                    relevant.append(tx)

            by_currency: dict[str, list[Transaction]] = defaultdict(list)
            for tx in relevant:
                by_currency[tx.currency].append(tx)
            best_x = Decimal("-1")
            best_evidence: list[Transaction] = []
            best_details: dict[str, Any] = {}
            for currency, limit in values["limits"].items():
                currency_txs = by_currency.get(currency, [])
                incoming = [
                    tx for tx in currency_txs if tx.receiver_account_id in account_ids
                ]
                outgoing = [
                    tx for tx in currency_txs if tx.sender_account_id in account_ids
                ]
                incoming_total = sum((tx.amount for tx in incoming), Decimal("0"))
                outgoing_total = sum((tx.amount for tx in outgoing), Decimal("0"))
                if (
                    incoming_total < Decimal(str(limit))
                    or incoming_total == 0
                    or outgoing_total == 0
                ):
                    continue
                ratio = outgoing_total / incoming_total
                if not Decimal(str(values["ratio_low"])) <= ratio <= Decimal(
                    str(values["ratio_high"])
                ):
                    continue
                first_outgoing_to_recipient: dict[int, datetime] = {}
                for tx in transactions:
                    if (
                        tx.sender_account_id in account_ids
                        and tx.tx_time < as_of
                        and tx.currency == currency
                        and tx.receiver_account_id not in cash_ids
                        and tx.sender_account.customer_id != tx.receiver_account.customer_id
                    ):
                        first_outgoing_to_recipient[tx.receiver_account_id] = min(
                            first_outgoing_to_recipient.get(
                                tx.receiver_account_id, tx.tx_time
                            ),
                            tx.tx_time,
                        )
                new_outgoing = [
                    tx
                    for tx in outgoing
                    if first_outgoing_to_recipient.get(tx.receiver_account_id)
                    is not None
                    and first_outgoing_to_recipient[tx.receiver_account_id]
                    >= window_start
                ]
                if not new_outgoing:
                    continue
                new_total = sum((tx.amount for tx in new_outgoing), Decimal("0"))
                x = new_total / outgoing_total if outgoing_total else Decimal("0")
                if x > best_x:
                    best_x = x
                    best_evidence = currency_txs
                    best_details = {
                        "currency": currency,
                        "incoming_total": str(incoming_total),
                        "outgoing_total": str(outgoing_total),
                        "outgoing_incoming_ratio": str(ratio),
                        "new_recipient_outflow": str(new_total),
                        "new_recipient_share": str(x),
                    }
            suppress = not best_details
            if suppress:
                best_x = Decimal("0")
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=best_x,
                    transactions=best_evidence,
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "window_start": window_start.isoformat(),
                            "window_hours": values["window_hours"],
                            "transaction_count": len(relevant),
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": best_details},
                        {"step": 3, "text": self.definition.steps[2], "status": (
                            "blocked" if suppress else "pending_shared_scoring"
                        ), "details": {"score_forced_to_zero": suppress}},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=suppress,
                )
            )
        return results
