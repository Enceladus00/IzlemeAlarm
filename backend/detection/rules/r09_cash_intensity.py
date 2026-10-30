from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R09Values
from backend.detection.rules.common import calendar_window_start
from backend.models import Customer, Transaction


class CashIntensityRule(RuleStrategy):
    definition = RuleDefinition(
        code="R09",
        name="Nakit yoğunluğu",
        description="Son dönemde nakdin toplam müşteri hareketindeki payını önceki dönemin payıyla karşılaştırır.",
        steps=(
            "Şimdiki ve önceki dönem işlemlerini müşteri ve para birimine göre ayır.",
            "Dönem toplamlarını ve seçili nakit kanallarındaki tutarları hesapla.",
            "Asgari nakit hacmini doğrula ve nakit payı değişimini sigmoid ile puanla.",
        ),
        alert_mode="ALERT",
        parameter_model=R09Values,
        parameters=(
            ParameterSpec("window_days", "integer", "days", "Current period length.", True),
            ParameterSpec("baseline_days", "integer", "days", "Immediately preceding comparison period length.", True),
            ParameterSpec("cash_channels", "list[channel]", "channel", "Channels considered cash.", True),
            ParameterSpec("limits", "map[currency, decimal]", "currency", "Minimum current-period cash volume required by currency.", True),
            ParameterSpec("x_esik", "decimal", "share delta", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "decimal", "share delta", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "The specification compares raw ratios; it does not normalize different period lengths, so use cautiously when baseline_days and window_days differ substantially.",
            "Internal transfers are excluded to avoid inflating both total and cash activity.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="Transaction channels and currency-specific totals exist, but channel classification and period comparability need analyst approval.",
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
            current_start = calendar_window_start(as_of, int(values["window_days"]))
            baseline_start = current_start - timedelta(days=int(values["baseline_days"]))
            account_ids = {account.account_id for account in customer.accounts if account.is_active}
            current: dict[str, list[Transaction]] = defaultdict(list)
            baseline: dict[str, list[Transaction]] = defaultdict(list)
            for transaction in transactions:
                sender_id = transaction.sender_account_id
                receiver_id = transaction.receiver_account_id
                if sender_id not in account_ids and receiver_id not in account_ids:
                    continue
                if (
                    sender_id in account_ids
                    and receiver_id in account_ids
                ) or transaction.tx_time >= as_of:
                    continue
                if current_start <= transaction.tx_time:
                    current[transaction.currency].append(transaction)
                elif baseline_start <= transaction.tx_time:
                    baseline[transaction.currency].append(transaction)

            best_x = Decimal("-2")
            best_evidence: list[Transaction] = []
            best_details: dict[str, Any] = {}
            for currency, limit in values["limits"].items():
                now_txs = current.get(currency, [])
                old_txs = baseline.get(currency, [])
                now_total = sum((tx.amount for tx in now_txs), Decimal("0"))
                old_total = sum((tx.amount for tx in old_txs), Decimal("0"))
                channels = set(values["cash_channels"])
                now_cash_txs = [tx for tx in now_txs if tx.channel in channels]
                old_cash_txs = [tx for tx in old_txs if tx.channel in channels]
                now_cash = sum((tx.amount for tx in now_cash_txs), Decimal("0"))
                old_cash = sum((tx.amount for tx in old_cash_txs), Decimal("0"))
                if now_cash < Decimal(str(limit)):
                    continue
                now_share = now_cash / now_total if now_total else Decimal("0")
                old_share = old_cash / old_total if old_total else Decimal("0")
                x = now_share - old_share
                if x > best_x:
                    best_x = x
                    best_evidence = now_cash_txs
                    best_details = {
                        "currency": currency,
                        "current_total": str(now_total),
                        "current_cash_total": str(now_cash),
                        "baseline_total": str(old_total),
                        "baseline_cash_total": str(old_cash),
                        "current_cash_share": str(now_share),
                        "baseline_cash_share": str(old_share),
                        "minimum_cash_volume": str(limit),
                    }
            suppress = not best_evidence
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
                            "current_start": current_start.isoformat(),
                            "baseline_start": baseline_start.isoformat(),
                            "window_days": values["window_days"],
                            "baseline_days": values["baseline_days"],
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
