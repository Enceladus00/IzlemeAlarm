import math
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import S2Values
from backend.detection.rules.common import calendar_window_start, median_and_mad
from backend.models import Customer, Transaction


MAD_SCALE = 1.4826  # makes the MAD comparable to a standard deviation


class HubAccountSignal(RuleStrategy):
    definition = RuleDefinition(
        code="S2",
        name="Merkez hesap",
        description="Müşterinin farklı karşı taraf sayısını aynı tipteki müşterilerle karşılaştırır; yalnızca birleşik skora (R18) katkı verir.",
        steps=(
            "Pencere içinde her müşterinin farklı karşı taraf hesaplarını say (kendi ve kasa hesapları hariç).",
            "Aynı müşteri tipindeki grubun log(1 + sayı) medyanını ve MAD değerini hesapla (MAD alt sınırı uygulanır).",
            "Müşterinin robust z değerini hesapla.",
            "z değerini ortak skor fonksiyonuyla skora çevir.",
        ),
        alert_mode="SIGNAL_ONLY",
        parameter_model=S2Values,
        parameters=(
            ParameterSpec("window_days", "integer", "days", "Calendar-day lookback including the run date.", False),
            ParameterSpec("mad_floor", "decimal", "log count", "Lower bound for the group MAD.", True),
            ParameterSpec("cash_accounts", "account ID list", "account_id", "Accounts excluded from counterparty counts.", False),
            ParameterSpec("x_esik", "decimal", "robust z", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "decimal", "robust z", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "Signal only: never opens an alert on its own; its score contributes to R18.",
            "The peer group is the set of customers of the same type evaluated in the same run.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="Peer statistics depend on how many customers of the same type are loaded.",
    )

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: datetime,
        context: Any = None,
    ) -> list[RawRuleResult]:
        if not customers:
            return []
        group_values = parameter_sets[customers[0].customer_type]["values"]
        window_start = calendar_window_start(as_of, int(group_values["window_days"]))
        excluded = set(group_values["cash_accounts"])
        counterparties: dict[int, set[int]] = {}
        evidence: dict[int, list[Transaction]] = {}
        window = [tx for tx in transactions if window_start <= tx.tx_time < as_of]
        for customer in customers:
            accounts = {account.account_id for account in customer.accounts if account.is_active}
            others: set[int] = set()
            used: list[Transaction] = []
            for tx in window:
                if tx.sender_account_id in accounts:
                    other = tx.receiver_account_id
                elif tx.receiver_account_id in accounts:
                    other = tx.sender_account_id
                else:
                    continue
                if other in accounts or other in excluded:
                    continue
                others.add(other)
                used.append(tx)
            counterparties[customer.customer_id] = others
            evidence[customer.customer_id] = used
        logs = [math.log1p(len(items)) for items in counterparties.values()]
        center, mad = median_and_mad(logs)
        scale = max(mad * MAD_SCALE, float(group_values["mad_floor"]))
        results = []
        for customer in customers:
            values = parameter_sets[customer.customer_type]["values"]
            count = len(counterparties[customer.customer_id])
            z = (math.log1p(count) - center) / scale
            raw_x = Decimal(str(round(z, 6)))
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=raw_x,
                    transactions=evidence[customer.customer_id] if z > 0 else [],
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "window_start": window_start.isoformat(),
                            "counterparty_count": count,
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "group_size": len(customers),
                            "group_median_log": round(center, 6),
                            "group_mad_log": round(mad, 6),
                            "scale": round(scale, 6),
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": "completed", "details": {
                            "x": str(raw_x),
                        }},
                        {"step": 4, "text": self.definition.steps[3], "status": "pending_shared_scoring", "details": {}},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                )
            )
        return results
