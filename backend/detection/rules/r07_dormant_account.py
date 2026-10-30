from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R07Values
from backend.detection.rules.common import calendar_window_start
from backend.models import Customer, Transaction


class DormantAccountRule(RuleStrategy):
    definition = RuleDefinition(
        code="R07",
        name="Uyuyan hesap uyanması",
        description="Uzun süredir hareketsiz hesaplarda bu hafta limitlere göre yüksek hareketi arar.",
        steps=(
            "Hesap bazında bu haftaki işlemleri seç.",
            "Pencere öncesi son işlemin tarihini ve hareketsizlik süresini hesapla.",
            "Hareketsizliği geçen hesapların para birimi toplamlarını limitlere oranla.",
            "Müşteri için en yüksek hesap skorunu kullan.",
        ),
        alert_mode="ALERT",
        parameter_model=R07Values,
        parameters=(
            ParameterSpec("dormant_days", "integer", "days", "Minimum inactivity gap before the current window.", True),
            ParameterSpec("window_days", "integer", "days", "Current activity window including run date.", True),
            ParameterSpec("limits", "map[currency, decimal]", "currency", "Reference amounts E by transaction currency.", True),
            ParameterSpec("x_esik", "decimal", "log ratio", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "decimal", "log ratio", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "Account-age and ownership lifecycle data must be accurate; activity is measured from active transaction records only.",
        ),
        feasibility="HIGH",
        feasibility_reason="Uses available account ownership, transaction dates, currencies, and configurable amount references.",
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
            window_start = calendar_window_start(as_of, int(values["window_days"]))
            customer_accounts = {
                account.account_id for account in customer.accounts if account.is_active
            }
            relevant = [
                transaction
                for transaction in transactions
                if transaction.tx_time < as_of
                and transaction.sender_account.customer_id
                != transaction.receiver_account.customer_id
                and (
                    transaction.sender_account_id in customer_accounts
                    or transaction.receiver_account_id in customer_accounts
                )
            ]
            best_x = Decimal("-100")
            best_evidence: list[Transaction] = []
            best_trace: dict[str, Any] = {}
            for account_id in customer_accounts:
                current = [
                    transaction
                    for transaction in relevant
                    if window_start <= transaction.tx_time
                    and (
                        transaction.sender_account_id == account_id
                        or transaction.receiver_account_id == account_id
                    )
                ]
                if not current:
                    continue
                previous = [
                    transaction.tx_time
                    for transaction in relevant
                    if transaction.tx_time < window_start
                    and (
                        transaction.sender_account_id == account_id
                        or transaction.receiver_account_id == account_id
                    )
                ]
                if not previous:
                    continue
                first_current = min(transaction.tx_time for transaction in current)
                dormant_gap = first_current - max(previous)
                if dormant_gap < timedelta(days=int(values["dormant_days"])):
                    continue
                totals: dict[str, Decimal] = defaultdict(Decimal)
                by_currency: dict[str, list[Transaction]] = defaultdict(list)
                for transaction in current:
                    totals[transaction.currency] += transaction.amount
                    by_currency[transaction.currency].append(transaction)
                for currency, total in totals.items():
                    reference = values["limits"].get(currency)
                    if reference is None or total <= 0:
                        continue
                    x = (total / Decimal(str(reference))).ln()
                    if x > best_x:
                        best_x = x
                        best_evidence = by_currency[currency]
                        best_trace = {
                            "account_id": account_id,
                            "currency": currency,
                            "total": str(total),
                            "reference_limit": str(reference),
                            "first_current": first_current.isoformat(),
                            "previous_activity": max(previous).isoformat(),
                            "dormant_gap_days": dormant_gap.total_seconds() / 86400,
                        }
            if best_x == Decimal("-100"):
                best_x = Decimal("0")
            suppress = not best_evidence
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=best_x,
                    transactions=best_evidence,
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "window_start": window_start.isoformat(),
                            "customer_account_count": len(customer_accounts),
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            **best_trace,
                            "dormant_days_threshold": values["dormant_days"],
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": (
                            "blocked" if suppress else "completed"
                        ), "details": {"score_forced_to_zero": suppress}},
                        {"step": 4, "text": self.definition.steps[3], "status": (
                            "blocked" if suppress else "pending_shared_scoring"
                        ), "details": {"x": str(best_x)}},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=suppress,
                )
            )
        return results
