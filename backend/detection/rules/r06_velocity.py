import math
from datetime import datetime, time, timedelta
from decimal import Decimal
from statistics import fmean, pvariance
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R06Values
from backend.detection.rules.common import distribution_survival
from backend.models import Customer, Transaction


class VelocityIncreaseRule(RuleStrategy):
    definition = RuleDefinition(
        code="R06",
        name="Hız artışı",
        description="Bu haftaki transfer sayısını önceki haftalık sayımlardan türetilen Poisson/negatif binom dağılımıyla karşılaştırır.",
        steps=(
            "Bu haftanın ve önceki tam haftaların müşteri işlem sayılarını hesapla.",
            "Geçmiş haftalardan ortalama ve varyansı; varsa mevsim katsayısıyla hesapla.",
            "Poisson veya negatif binom üst-kuyruk olasılığını bul.",
            "−log10(p) değerini sigmoid ile puanla.",
        ),
        alert_mode="ALERT",
        parameter_model=R06Values,
        parameters=(
            ParameterSpec("history_weeks", "integer", "weeks", "Number of complete prior weeks used as baseline.", True),
            ParameterSpec("min_count", "integer", "transactions", "Minimum current-week count before scoring.", True),
            ParameterSpec("season_factor", "date-to-decimal map", "date:factor", "Optional week-ending dates and positive count multipliers.", False),
            ParameterSpec("x_esik", "decimal", "-log10 probability", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "decimal", "-log10 probability", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "Distribution tails use an in-project standard-library implementation of Poisson/negative-binomial survival probabilities rather than SciPy; review calibration against validated reference data before approval.",
            "Transfers between accounts owned by the same customer are excluded to avoid counting internal movements as velocity.",
            "The weekly baseline treats weeks without recorded transfers as zero; validate transaction-history coverage before interpreting a spike.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="All required transaction history exists, but distribution-tail calibration and seasonality quality require validation.",
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
            week_start = datetime.combine(
                as_of.date() - timedelta(days=as_of.date().weekday()),
                time.min,
            )
            all_weekly_counts: list[int] = []
            for week_index in range(int(values["history_weeks"]), 0, -1):
                start = week_start - timedelta(days=7 * week_index)
                end = start + timedelta(days=7)
                week_transactions = [
                    transaction
                    for transaction in transactions
                    if start <= transaction.tx_time < end
                    and transaction.sender_account.customer_id
                    != transaction.receiver_account.customer_id
                    and customer.customer_id
                    in {
                        transaction.sender_account.customer_id,
                        transaction.receiver_account.customer_id,
                    }
                ]
                all_weekly_counts.append(len(week_transactions))
            current_transactions = [
                transaction
                for transaction in transactions
                if week_start <= transaction.tx_time < as_of
                and transaction.sender_account.customer_id
                != transaction.receiver_account.customer_id
                and customer.customer_id
                in {
                    transaction.sender_account.customer_id,
                    transaction.receiver_account.customer_id,
                }
            ]
            n = len(current_transactions)
            lam = fmean(all_weekly_counts) if all_weekly_counts else 0.0
            variance = pvariance(all_weekly_counts) if all_weekly_counts else 0.0
            week_end = (week_start + timedelta(days=6)).date()
            seasonal_factors = values["season_factor"]
            factor = float(seasonal_factors.get(week_end.isoformat(), 1))
            lam *= factor
            if lam == 0:
                lam = 0.5
            p = (
                distribution_survival(n, lam, variance)
                if n >= int(values["min_count"])
                else 1.0
            )
            x = Decimal(str(-math.log10(p)))
            suppress = n < int(values["min_count"])
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=x,
                    transactions=current_transactions,
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "week_start": week_start.isoformat(),
                            "history_weekly_counts": all_weekly_counts,
                            "current_week_count": n,
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "lambda": lam,
                            "variance": variance,
                            "season_factor": factor,
                            "week_ending": week_end.isoformat(),
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": "completed", "details": {
                            "tail_probability": p,
                            "distribution": "poisson" if variance <= lam else "negative_binomial",
                        }},
                        {"step": 4, "text": self.definition.steps[3], "status": (
                            "blocked" if suppress else "pending_shared_scoring"
                        ), "details": {
                            "x": str(x),
                            "minimum_count_met": not suppress,
                        }},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=suppress,
                )
            )
        return results
