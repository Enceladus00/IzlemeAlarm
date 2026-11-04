from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R16Values
from backend.detection.rules.common import calendar_window_start
from backend.models import Customer, Transaction


class ListedCountryRule(RuleStrategy):
    definition = RuleDefinition(
        code="R16",
        name="Listelenmiş ülke",
        description="Listelenmiş (yüksek riskli) ülkelerle yapılan işlemlerin hacmini referans tutara oranlar.",
        steps=(
            "Pencere içinde müşterinin listelenmiş ülkelerle yaptığı gelen ve giden işlemleri seç.",
            "Para birimi bazında toplam tutarı (T) hesapla.",
            "Her para birimi için ln(T / E) değerini hesapla; en yükseğini kullan.",
            "Ham değeri ortak skor fonksiyonuyla skora çevir.",
        ),
        alert_mode="ALERT",
        parameter_model=R16Values,
        parameters=(
            ParameterSpec("countries", "list[ISO 3166 alpha-2]", "country", "Listed (high-risk) countries.", True),
            ParameterSpec("limits", "map[currency, decimal]", "currency", "Reference amounts E by transaction currency.", True),
            ParameterSpec("window_days", "integer", "days", "Calendar-day lookback including the run date.", True),
            ParameterSpec("x_esik", "decimal", "log ratio", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "decimal", "log ratio", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "The transaction's country_code is used as the counterparty country; transfers between the customer's own accounts are ignored.",
            "Replaces legacy rule R4 (high-risk country).",
        ),
        feasibility="HIGH",
        feasibility_reason="Uses transaction country codes, currencies and configurable reference amounts.",
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
            countries = set(values["countries"])
            window_start = calendar_window_start(as_of, int(values["window_days"]))
            accounts = {account.account_id for account in customer.accounts if account.is_active}
            relevant = [
                tx
                for tx in transactions
                if window_start <= tx.tx_time < as_of
                and tx.country_code in countries
                and tx.sender_account.customer_id != tx.receiver_account.customer_id
                and (tx.sender_account_id in accounts or tx.receiver_account_id in accounts)
            ]
            totals: dict[str, Decimal] = defaultdict(Decimal)
            by_currency: dict[str, list[Transaction]] = defaultdict(list)
            for tx in relevant:
                totals[tx.currency] += tx.amount
                by_currency[tx.currency].append(tx)
            best_x: Decimal | None = None
            best: dict[str, Any] = {}
            ignored = 0
            for currency, total in totals.items():
                reference = values["limits"].get(currency)
                if reference is None:
                    ignored += len(by_currency[currency])
                    continue
                x = (total / Decimal(str(reference))).ln()
                if best_x is None or x > best_x:
                    best_x = x
                    best = {
                        "currency": currency,
                        "total": str(total),
                        "reference_limit": str(reference),
                        "transaction_count": len(by_currency[currency]),
                    }
            suppress = best_x is None
            raw_x = Decimal("0") if best_x is None else best_x
            evidence = by_currency[best["currency"]] if best else []
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=raw_x,
                    transactions=evidence,
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "window_start": window_start.isoformat(),
                            "window_days": values["window_days"],
                            "countries": sorted(countries),
                            "listed_transaction_count": len(relevant),
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "totals": {currency: str(total) for currency, total in totals.items()},
                            "unlisted_currency_transaction_count": ignored,
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": (
                            "blocked" if suppress else "completed"
                        ), "details": {**best, "x": str(raw_x), "score_forced_to_zero": suppress}},
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
