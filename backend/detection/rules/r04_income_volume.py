from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R04Values
from backend.detection.rules.common import calendar_window_start
from backend.models import Customer, Transaction


class IncomeVolumeRule(RuleStrategy):
    definition = RuleDefinition(
        code="R04",
        name="Gelir-hacim uyumsuzluğu",
        description="Aylık gelir ile son dönemdeki en yüksek dış transfer yönü toplamını karşılaştırır.",
        steps=(
            "Gelir ve ayarlı takvim-günü penceresini belirle.",
            "Müşterinin dışarı giden ve gelen TRY toplamlarını hesapla.",
            "x = max(outgoing, incoming) / monthly_income.",
            "Sigmoid skoru hesapla; eksik veya sıfır gelirde skoru engelle.",
        ),
        alert_mode="ALERT",
        parameter_model=R04Values,
        parameters=(
            ParameterSpec("window_days", "integer", "days", "Calendar-day lookback including run date.", True),
            *(
                ParameterSpec(name, "decimal", "ratio", f"Score anchor {name}.", True)
                for name in ("x_esik", "x_kesin")
            ),
        ),
        analyst_review_notes=(
            "Income currency is not represented in customer data; the specification currently assumes TRY income and TRY transactions.",
            "This rule intentionally has no linked transaction evidence because it is aggregate-based; analysts must inspect customer activity and the stored calculation trace.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="The required data exists, but monthly income has no stored currency and the rule currently assumes TRY.",
    )

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: datetime,
    ) -> list[RawRuleResult]:
        windows = {
            customer.customer_id: calendar_window_start(
                as_of, int(parameter_sets[customer.customer_type]["values"]["window_days"])
            )
            for customer in customers
        }
        by_customer: dict[int, tuple[Decimal, Decimal]] = defaultdict(
            lambda: (Decimal("0"), Decimal("0"))
        )
        customer_ids = {customer.customer_id for customer in customers}
        for transaction in transactions:
            if transaction.currency != "TRY" or not (
                windows.get(transaction.sender_account.customer_id, as_of)
                <= transaction.tx_time
                < as_of
                or windows.get(transaction.receiver_account.customer_id, as_of)
                <= transaction.tx_time
                < as_of
            ):
                continue
            sender_id = transaction.sender_account.customer_id
            receiver_id = transaction.receiver_account.customer_id
            if sender_id == receiver_id:
                continue
            if sender_id in customer_ids and transaction.tx_time >= windows[sender_id]:
                outgoing, incoming = by_customer[sender_id]
                by_customer[sender_id] = outgoing + transaction.amount, incoming
            if receiver_id in customer_ids and transaction.tx_time >= windows[receiver_id]:
                outgoing, incoming = by_customer[receiver_id]
                by_customer[receiver_id] = outgoing, incoming + transaction.amount

        results = []
        for customer in customers:
            values = parameter_sets[customer.customer_type]["values"]
            outgoing, incoming = by_customer[customer.customer_id]
            income = customer.monthly_income
            valid_income = income is not None and income > 0
            x = max(outgoing, incoming) / income if valid_income else Decimal("0")
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=x,
                    transactions=[],
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "window_start": windows[customer.customer_id].isoformat(),
                            "window_days": values["window_days"],
                            "monthly_income_available": valid_income,
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "outgoing_try_total": str(outgoing),
                            "incoming_try_total": str(incoming),
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": "completed", "details": {
                            "x": str(x),
                        }},
                        {"step": 4, "text": self.definition.steps[3], "status": (
                            "pending_shared_scoring" if valid_income else "blocked"
                        ), "details": {
                            "analyst_review_required": not valid_income,
                            "score_forced_to_zero": not valid_income,
                        }},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=not valid_income,
                )
            )
        return results
