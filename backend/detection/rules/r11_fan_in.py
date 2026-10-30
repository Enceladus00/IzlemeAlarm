from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R11Values
from backend.detection.rules.common import calendar_window_start
from backend.models import Customer, Transaction


class FanInRule(RuleStrategy):
    definition = RuleDefinition(
        code="R11",
        name="Para toplama (fan-in)",
        description="Kısa sürede ilk kez temas edilen çok sayıda kaynaktan gelen transferleri bulur.",
        steps=(
            "Gelen işlemleri ayarlı takvim-günü penceresinde seç.",
            "Nakit hesapları ve müşterinin kendi hesapları arasındaki transferleri çıkar.",
            "Yeni gönderen sayısını sigmoid ile puanla.",
        ),
        alert_mode="ALERT",
        parameter_model=R11Values,
        parameters=(
            ParameterSpec("window_days", "integer", "days", "Calendar-day lookback including run date.", True),
            ParameterSpec("cash_accounts", "account ID list", "account_id", "Sender accounts excluded as cash/custody accounts.", False),
            ParameterSpec("x_esik", "integer", "sender count", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "integer", "sender count", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "A sender is an account ID, not a customer ID, because the rule specification counts unique sender accounts.",
            "Cash-account classification is maintained in rule configuration and must be approved by an analyst.",
            "An absent historical transfer is treated as a first contact; validate transaction-history coverage to avoid classifying old senders as new.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="Uses transaction counterpart accounts and historical first-contact dates; cash-account exclusions must be configured.",
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
            incoming = [
                tx
                for tx in transactions
                if window_start <= tx.tx_time < as_of
                and tx.receiver_account_id in account_ids
                and tx.sender_account_id not in cash_accounts
                and tx.sender_account.customer_id != customer.customer_id
            ]
            first_from_sender: dict[int, datetime] = {}
            for tx in transactions:
                if (
                    tx.tx_time < as_of
                    and
                    tx.sender_account_id not in cash_accounts
                    and tx.receiver_account_id in account_ids
                    and tx.sender_account.customer_id != customer.customer_id
                ):
                    first_from_sender[tx.sender_account_id] = min(
                        first_from_sender.get(tx.sender_account_id, tx.tx_time),
                        tx.tx_time,
                    )
            new_transactions = [
                tx
                for tx in incoming
                if first_from_sender.get(tx.sender_account_id, as_of) >= window_start
            ]
            new_sender_ids = {tx.sender_account_id for tx in new_transactions}
            x = Decimal(len(new_sender_ids))
            suppress = not new_sender_ids
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=x,
                    transactions=new_transactions,
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "window_start": window_start.isoformat(),
                            "incoming_transaction_count": len(incoming),
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "cash_accounts": sorted(cash_accounts),
                            "new_sender_count": len(new_sender_ids),
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": (
                            "blocked" if suppress else "pending_shared_scoring"
                        ), "details": {"x": str(x), "score_forced_to_zero": suppress}},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=suppress,
                )
            )
        return results
