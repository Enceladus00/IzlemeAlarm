from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import S1Values
from backend.detection.rules.common import calendar_window_start
from backend.models import Customer, Transaction


class RoundAmountsSignal(RuleStrategy):
    definition = RuleDefinition(
        code="S1",
        name="Yuvarlak tutar",
        description="Büyük tutarlı giden işlemlerin ne kadarının yuvarlak tutarda olduğunu ölçer; yalnızca birleşik skora (R18) katkı verir.",
        steps=(
            "Pencere içindeki giden işlemlerden para birimine göre büyük tutar sınırını (B) aşanları seç.",
            "Bunların kaçının yuvarlama biriminin tam katı olduğunu say.",
            "Yuvarlak işlem payını hesapla; büyük işlem sayısı en az sayının altındaysa sinyal üretme.",
            "Payı ortak skor fonksiyonuyla skora çevir.",
        ),
        alert_mode="SIGNAL_ONLY",
        parameter_model=S1Values,
        parameters=(
            ParameterSpec("limits", "map[currency, decimal]", "currency", "Big-amount threshold B by currency.", True),
            ParameterSpec("round_unit", "decimal", "currency unit", "An amount is round when it is an exact multiple of this unit.", True),
            ParameterSpec("min_count", "integer", "transactions", "Minimum number of big transactions before a share is meaningful.", True),
            ParameterSpec("window_days", "integer", "days", "Calendar-day lookback including the run date.", False),
            ParameterSpec("x_esik", "decimal", "share 0-1", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "decimal", "share 0-1", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "Signal only: never opens an alert on its own; its score contributes to R18.",
            "Only outgoing transactions to other customers are considered.",
        ),
        feasibility="HIGH",
        feasibility_reason="Uses transaction amounts and currencies only.",
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
        results = []
        for customer in customers:
            values = parameter_sets[customer.customer_type]["values"]
            window_start = calendar_window_start(as_of, int(values["window_days"]))
            unit = Decimal(str(values["round_unit"]))
            limits = {code: Decimal(str(limit)) for code, limit in values["limits"].items()}
            accounts = {account.account_id for account in customer.accounts if account.is_active}
            outgoing = [
                tx
                for tx in transactions
                if window_start <= tx.tx_time < as_of
                and tx.sender_account_id in accounts
                and tx.receiver_account.customer_id != customer.customer_id
            ]
            ignored = sum(1 for tx in outgoing if tx.currency not in limits)
            big = [tx for tx in outgoing if tx.currency in limits and tx.amount >= limits[tx.currency]]
            round_big = [tx for tx in big if tx.amount % unit == 0]
            suppress = len(big) < int(values["min_count"])
            share = Decimal("0") if suppress or not big else Decimal(len(round_big)) / Decimal(len(big))
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=share,
                    transactions=[] if suppress else round_big,
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "window_start": window_start.isoformat(),
                            "outgoing_count": len(outgoing),
                            "big_count": len(big),
                            "unlisted_currency_transaction_count": ignored,
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "round_unit": str(unit),
                            "round_big_count": len(round_big),
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": (
                            "blocked" if suppress else "completed"
                        ), "details": {
                            "round_share": str(share),
                            "min_count": values["min_count"],
                            "score_forced_to_zero": suppress,
                        }},
                        {"step": 4, "text": self.definition.steps[3], "status": (
                            "blocked" if suppress else "pending_shared_scoring"
                        ), "details": {}},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=suppress,
                    ignored_currency_count=ignored,
                )
            )
        return results
