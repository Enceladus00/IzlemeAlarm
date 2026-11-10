import math
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import fmean, pvariance
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R06Values
from backend.detection.rules.common import calendar_window_start, distribution_survival
from backend.models import Customer, Transaction


class VelocityIncreaseRule(RuleStrategy):
    definition = RuleDefinition(
        code="R06",
        name="Hız artışı",
        description="Son 7 gündeki transfer sayısını önceki 7 günlük dilimlerin sayımlarından türetilen Poisson/negatif binom dağılımıyla karşılaştırır.",
        steps=(
            "Son 7 günün (bugün dahil) ve ondan önceki 7'şer günlük dilimlerin müşteri işlem sayılarını hesapla.",
            "Geçmiş dilimlerden ortalama ve varyansı; varsa mevsim katsayısı ve dalgalanma tabanıyla hesapla.",
            "Poisson veya negatif binom üst-kuyruk olasılığını bul.",
            "−log10(p) değerini sigmoid ile puanla.",
        ),
        alert_mode="ALERT",
        parameter_model=R06Values,
        parameters=(
            ParameterSpec("history_weeks", "integer", "weeks", "Number of prior 7-day slices used as baseline.", True),
            ParameterSpec("min_count", "integer", "transactions", "Minimum count in the last 7 days before scoring.", True),
            ParameterSpec("season_factor", "date-to-decimal map", "date:factor", "Optional dates and positive count multipliers; a factor applies while its date is within the last 7 days.", False),
            ParameterSpec("dispersion_k", "decimal", "dispersion", "Optional variance floor: variance >= mean + mean^2 / k. Empty = no floor.", False),
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
            # "This week" is the last 7 calendar days including the run date, so
            # the rule sees the same amount of activity on every weekday. The
            # history is the 7-day slices before that.
            week_start = calendar_window_start(as_of, 7)
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
            week_end = as_of.date()
            # A season factor applies while its date is inside the 7-day window.
            window_dates = {
                (week_start.date() + timedelta(days=offset)).isoformat()
                for offset in range(7)
            }
            factor = max(
                (
                    float(value)
                    for key, value in values["season_factor"].items()
                    if key in window_dates
                ),
                default=1.0,
            )
            lam *= factor
            if lam == 0:
                lam = 0.5
            history_variance = variance
            dispersion_k = values.get("dispersion_k")
            variance_floor = (
                lam + lam * lam / float(dispersion_k)
                if dispersion_k is not None
                else None
            )
            floor_applied = variance_floor is not None and variance < variance_floor
            if floor_applied:
                variance = variance_floor
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
                            "history_variance": history_variance,
                            "dispersion_k": (
                                str(dispersion_k) if dispersion_k is not None else None
                            ),
                            "variance_floor": variance_floor,
                            "variance_floor_applied": floor_applied,
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
