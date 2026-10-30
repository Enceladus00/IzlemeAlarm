import math
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R05Values
from backend.detection.rules.common import median_and_mad, prior_day_start
from backend.models import Customer, Transaction


class UnusualAmountRule(RuleStrategy):
    definition = RuleDefinition(
        code="R05",
        name="Olağandışı tutar",
        description="Bugünkü her transferi müşterinin geçmiş log-tutar dağılımına ve gelir grubuna göre değerlendirir.",
        steps=(
            "Bugün dışarı giden ve gelen işlemleri, geçmiş dönemden ayır.",
            "Geçmiş tutarların log-medyanı ve MAD değerini hesapla.",
            "Aynı müşteri tipi/gelir dilimindeki geçmişlerle kappa ağırlıklı temel değerleri hesapla.",
            "Bugünkü z-skorlarının en büyüğünü sigmoid ile puanla.",
        ),
        alert_mode="ALERT",
        parameter_model=R05Values,
        parameters=(
            ParameterSpec("history_days", "integer", "days", "Historical lookback; current run date is excluded.", True),
            ParameterSpec("kappa", "decimal", "weight", "Prior strength of peer-group baseline.", True),
            ParameterSpec("mad_floor", "decimal", "log amount", "Minimum robust dispersion to prevent unstable z-scores.", True),
            ParameterSpec("income_bands", "integer", "bands", "Number of equal-count income groups within each customer type.", True),
            ParameterSpec("x_esik", "decimal", "robust z-score", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "decimal", "robust z-score", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "Income bands are assigned by equal-count ranking (a deterministic qcut equivalent); ties may produce slightly different group boundaries than pandas qcut.",
            "Baselines are kept separate by transaction currency; no FX conversion is applied. Transfers between the same customer's accounts are excluded.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="Requires peer-group robust statistics and enough historical activity; the implementation uses a deterministic equal-count income ranking.",
    )

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: datetime,
    ) -> list[RawRuleResult]:
        by_customer: dict[int, list[Transaction]] = defaultdict(list)
        for transaction in transactions:
            sender_id = transaction.sender_account.customer_id
            receiver_id = transaction.receiver_account.customer_id
            if sender_id == receiver_id:
                continue
            by_customer[sender_id].append(transaction)
            by_customer[receiver_id].append(transaction)

        params = parameter_sets[customers[0].customer_type]["values"] if customers else {}
        if not customers:
            return []
        history_start = prior_day_start(as_of, int(params["history_days"]))
        today_start = datetime.combine(as_of.date(), datetime.min.time())
        logs: dict[tuple[int, str], list[float]] = defaultdict(list)
        today: dict[int, list[Transaction]] = {}
        for customer in customers:
            customer_transactions = by_customer[customer.customer_id]
            for transaction in customer_transactions:
                if (
                    history_start <= transaction.tx_time < today_start
                    and transaction.amount > 0
                ):
                    logs[(customer.customer_id, transaction.currency)].append(
                        math.log(float(transaction.amount))
                    )
            today[customer.customer_id] = [
                transaction
                for transaction in customer_transactions
                if today_start <= transaction.tx_time < as_of
            ]

        ranked_income = sorted(
            (
                customer.monthly_income,
                customer.customer_id,
            )
            for customer in customers
            if customer.monthly_income is not None
        )
        bands = int(params["income_bands"])
        income_band_by_customer = {
            customer_id: min(index * bands // max(1, len(ranked_income)), bands - 1)
            for index, (_, customer_id) in enumerate(ranked_income)
        }
        group_logs: dict[tuple[int, str], list[float]] = defaultdict(list)
        for (customer_id, currency), customer_logs in logs.items():
            band = income_band_by_customer.get(customer_id)
            if band is not None:
                group_logs[(band, currency)].extend(customer_logs)

        results = []
        for customer in customers:
            values = parameter_sets[customer.customer_type]["values"]
            kappa = float(values["kappa"])
            z_values: list[tuple[float, Transaction, dict[str, Any]]] = []
            total_history_count = sum(
                len(customer_logs)
                for (customer_id, _currency), customer_logs in logs.items()
                if customer_id == customer.customer_id
            )
            for transaction in today[customer.customer_id]:
                if transaction.amount <= 0:
                    continue
                own_logs = logs[(customer.customer_id, transaction.currency)]
                own_median, own_mad = (
                    median_and_mad(own_logs) if own_logs else (0.0, 0.0)
                )
                band = income_band_by_customer.get(customer.customer_id)
                group_history = (
                    group_logs.get((band, transaction.currency), [])
                    if band is not None
                    else []
                )
                if not group_history:
                    group_history = own_logs
                if not own_logs and not group_history:
                    continue
                peer_median, peer_mad = (
                    median_and_mad(group_history)
                    if group_history
                    else (own_median, own_mad)
                )
                n = len(own_logs)
                denominator = n + kappa
                if denominator == 0:
                    continue
                baseline_median = (
                    n * own_median + kappa * peer_median
                ) / denominator
                baseline_mad = max(
                    float(values["mad_floor"]),
                    (n * own_mad + kappa * peer_mad) / denominator,
                )
                z = (
                    math.log(float(transaction.amount)) - baseline_median
                ) / (1.4826 * baseline_mad)
                z_values.append(
                    (
                        z,
                        transaction,
                        {
                            "currency": transaction.currency,
                            "history_count": n,
                            "median_log_amount": own_median,
                            "mad_log_amount": own_mad,
                            "income_band": band,
                            "peer_median": peer_median,
                            "peer_mad": peer_mad,
                            "blended_median": baseline_median,
                            "blended_mad": baseline_mad,
                        },
                    )
                )
            if z_values:
                max_z, evidence_transaction, baseline_details = max(
                    z_values, key=lambda item: item[0]
                )
                x = Decimal(str(max_z))
                evidence = [evidence_transaction]
            else:
                x = Decimal("0")
                evidence = []
                baseline_details = {}
            suppress = not z_values
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=x,
                    transactions=evidence,
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "history_start": history_start.isoformat(),
                            "today_start": today_start.isoformat(),
                            "history_count": total_history_count,
                            "today_count": len(today[customer.customer_id]),
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            **baseline_details,
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": "completed", "details": {
                            "income_band": income_band_by_customer.get(customer.customer_id),
                            "income_bands": bands,
                            "currency_scoped_baseline": True,
                            "baseline_missing": suppress,
                        }},
                        {"step": 4, "text": self.definition.steps[3], "status": (
                            "blocked" if suppress else "pending_shared_scoring"
                        ), "details": {
                            "maximum_z": str(x),
                            "score_forced_to_zero": suppress,
                        }},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=suppress,
                )
            )
        return results
