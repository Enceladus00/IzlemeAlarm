from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from backend.detection.metadata import (
    ParameterSpec,
    RawRuleResult,
    RuleDefinition,
    RuleStrategy,
)
from backend.detection.parameters import R01Values
from backend.models import Customer, Transaction


class SplittingRule(RuleStrategy):
    definition = RuleDefinition(
        code="R01",
        name="Bölme - Limitin hemen altında birden çok işlem",
        description="Müşterinin gelir para birimindeki, limitin hemen altındaki giden işlemleri gün bazlı pencerede değerlendirir.",
        steps=(
            "Ayarlı gün penceresindeki gelir para birimli, dışarı giden işlemleri al.",
            "Tutarı [band_low*L, L) olan işlemleri say -> x ve tutarlarını topla.",
            "Ayarlı üst bantta işlem varsa veya gelir kontrolü skoru engelliyorsa s = 0.",
            "Değilse s = sigmoid((x - x_esik) / c).",
        ),
        alert_mode="ALERT",
        parameter_model=R01Values,
        parameters=(
            ParameterSpec("limits", "map[currency, decimal]", "currency", "R01 uses L for income_currency; no currency conversion is applied.", True),
            ParameterSpec("x_esik", "integer", "transaction count", "Score is 0.5 at this near-limit count.", True),
            ParameterSpec("x_kesin", "integer", "transaction count", "Score is 0.9 at this near-limit count; must exceed x_esik.", True),
            ParameterSpec("minimum_income_ratio", "decimal", "ratio", "Minimum band total divided by monthly income.", True),
            ParameterSpec("income_currency", "ISO currency", "currency", "Currency used for monthly_income; no FX conversion is applied.", True),
            ParameterSpec("window_days", "integer", "days", "Calendar-day lookback including the run date.", True),
            ParameterSpec("band_low", "decimal", "ratio", "Inclusive lower transaction bound as a fraction of limit L.", True),
            ParameterSpec("above_check", "decimal", "multiple", "Exclusive upper bound for the transaction check above L.", True),
        ),
        analyst_review_notes=(
            "Monthly-income handling is conservative: if income is missing or zero, R01 is suppressed to avoid raising an alert without the income check. An analyst should confirm this policy.",
            "Daily deduplication consolidates same-day R01 results into one alert, accumulates evidence, and keeps the highest score. An analyst should confirm whether distinct same-day episodes should instead create separate alerts.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="Transaction and income data are available, but monthly-income currency is not stored and requires an explicit institution assumption.",
    )

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: datetime,
    ) -> list[RawRuleResult]:
        customer_by_id = {customer.customer_id: customer for customer in customers}
        customer_parameters = {
            customer.customer_id: parameter_sets[customer.customer_type]["values"]
            for customer in customers
        }
        window_start_by_customer = {
            customer.customer_id: datetime.combine(
                as_of.date()
                - timedelta(
                    days=int(
                        customer_parameters[customer.customer_id].get(
                            "window_days", 7
                        )
                    )
                    - 1
                ),
                time.min,
            )
            for customer in customers
        }
        grouped: dict[tuple[int, str], list[Transaction]] = defaultdict(list)
        for transaction in transactions:
            sender_customer_id = transaction.sender_account.customer_id
            customer = customer_by_id.get(sender_customer_id)
            if customer is None:
                continue
            if not (
                window_start_by_customer[sender_customer_id]
                <= transaction.tx_time
                < as_of
            ):
                continue
            if transaction.receiver_account.customer_id == sender_customer_id:
                continue
            grouped[(sender_customer_id, transaction.currency)].append(transaction)

        results: list[RawRuleResult] = []
        for customer in customers:
            parameter_set = parameter_sets[customer.customer_type]
            values = parameter_set["values"]
            limits = {
                currency: Decimal(str(limit))
                for currency, limit in values["limits"].items()
            }
            income_currency = values["income_currency"]
            limit = limits[income_currency]
            currency_transactions = grouped.get(
                (customer.customer_id, income_currency), []
            )
            ignored_currency_count = sum(
                len(group)
                for (customer_id, currency), group in grouped.items()
                if customer_id == customer.customer_id and currency != income_currency
            )
            band = [
                transaction
                for transaction in currency_transactions
                if limit * Decimal(str(values.get("band_low", "0.9")))
                <= transaction.amount
                < limit
            ]
            upper_check = limit * Decimal(str(values.get("above_check", "1.1")))
            upper_band = [
                transaction
                for transaction in currency_transactions
                if limit <= transaction.amount < upper_check
            ]
            raw_x = Decimal(len(band))
            band_total = sum(
                (transaction.amount for transaction in band), Decimal("0")
            )
            income = customer.monthly_income
            income_available = income is not None and income > 0
            income_ratio = band_total / income if income_available else None
            income_ratio_too_small = (
                income_ratio is not None
                and income_ratio < Decimal(str(values["minimum_income_ratio"]))
            )
            income_check_unavailable = not income_available
            force_zero = bool(
                upper_band or income_ratio_too_small or income_check_unavailable
            )
            trace = [
                {
                    "step": 1,
                    "text": self.definition.steps[0],
                    "status": "completed",
                    "details": {
                        "window_start": window_start_by_customer[
                            customer.customer_id
                        ].isoformat(),
                        "as_of": as_of.isoformat(),
                        "window_days": values["window_days"],
                        "transaction_count": len(currency_transactions),
                        "currency": income_currency,
                        "non_income_currency_transaction_count": ignored_currency_count,
                    },
                },
                {
                    "step": 2,
                    "text": self.definition.steps[1],
                    "status": "completed",
                    "details": {
                        "limit": str(limit),
                        "band_low": str(values.get("band_low", "0.9")),
                        "band_lower_inclusive": str(
                            limit * Decimal(str(values.get("band_low", "0.9")))
                        ),
                        "band_upper_exclusive": str(limit),
                        "x": int(raw_x),
                        "band_total": str(band_total),
                    },
                },
                {
                    "step": 3,
                    "text": self.definition.steps[2],
                    "status": "blocked" if force_zero else "passed",
                    "details": {
                        "above_check": str(values.get("above_check", "1.1")),
                        "upper_check_exclusive": str(upper_check),
                        "upper_band_transaction_count": len(upper_band),
                        "income_currency": income_currency,
                        "monthly_income_available": income_available,
                        "income_check_unavailable": income_check_unavailable,
                        "income_ratio": (
                            str(income_ratio) if income_ratio is not None else None
                        ),
                        "minimum_income_ratio": str(values["minimum_income_ratio"]),
                        "analyst_review_required": income_check_unavailable,
                        "score_forced_to_zero": force_zero,
                    },
                },
                {
                    "step": 4,
                    "text": self.definition.steps[3],
                    "status": "pending_shared_scoring",
                    "details": {},
                },
            ]
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=raw_x,
                    transactions=band,
                    step_trace=trace,
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=force_zero,
                    ignored_currency_count=ignored_currency_count,
                )
            )
        return results
