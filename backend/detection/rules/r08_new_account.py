from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R08Values
from backend.models import Customer, Transaction


class NewAccountActivityRule(RuleStrategy):
    definition = RuleDefinition(
        code="R08",
        name="Yeni hesapta yüksek hareket",
        description="Yakın zamanda açılmış hesapların açılıştan bugüne transfer hacmini limitlerine göre değerlendirir.",
        steps=(
            "Açılış tarihi ayarlı yaş sınırından yeni olan hesapları seç.",
            "Hesap açılışından itibaren aktif transfer hacmini para birimine göre topla.",
            "Hacmi limitin doğal logaritmalı oranına çevir ve müşteri için en yüksek skoru kullan.",
        ),
        alert_mode="ALERT",
        parameter_model=R08Values,
        parameters=(
            ParameterSpec("account_age_days", "integer", "days", "Maximum account age to consider.", True),
            ParameterSpec("limits", "map[currency, decimal]", "currency", "Reference amounts E by transaction currency.", True),
            ParameterSpec("x_esik", "decimal", "log ratio", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "decimal", "log ratio", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "Account opening dates are date-only; transfers on the opening date are included, and dates at the age cutoff are excluded.",
        ),
        feasibility="HIGH",
        feasibility_reason="Account opening dates and transaction histories are available; missing opening dates are skipped.",
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
        run_date = as_of.date()
        for customer in customers:
            values = parameter_sets[customer.customer_type]["values"]
            age_cutoff = run_date - timedelta(days=int(values["account_age_days"]))
            totals: dict[tuple[int, str], Decimal] = defaultdict(Decimal)
            evidence_by_key: dict[tuple[int, str], list[Transaction]] = defaultdict(list)
            new_accounts = [
                account
                for account in customer.accounts
                if account.is_active and account.opened_at is not None and account.opened_at > age_cutoff
            ]
            new_account_ids = {account.account_id for account in new_accounts}
            for transaction in transactions:
                if transaction.tx_time >= as_of:
                    continue
                if (
                    transaction.sender_account.customer_id
                    == transaction.receiver_account.customer_id
                ):
                    continue
                involved = {
                    transaction.sender_account_id,
                    transaction.receiver_account_id,
                } & new_account_ids
                for account_id in involved:
                    opened_at = next(
                        account.opened_at
                        for account in new_accounts
                        if account.account_id == account_id
                    )
                    if transaction.tx_time.date() < opened_at:
                        continue
                    key = (account_id, transaction.currency)
                    totals[key] += transaction.amount
                    evidence_by_key[key].append(transaction)
            best_x = Decimal("-100")
            best_evidence: list[Transaction] = []
            best_details: dict[str, Any] = {}
            for key, total in totals.items():
                reference = values["limits"].get(key[1])
                if reference is None or total <= 0:
                    continue
                x = (total / Decimal(str(reference))).ln()
                if x > best_x:
                    best_x = x
                    best_evidence = evidence_by_key[key]
                    best_details = {
                        "account_id": key[0],
                        "currency": key[1],
                        "total_volume": str(total),
                        "reference_limit": str(reference),
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
                            "age_cutoff_exclusive": age_cutoff.isoformat(),
                            "new_account_count": len(new_accounts),
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": best_details},
                        {"step": 3, "text": self.definition.steps[2], "status": (
                            "blocked" if suppress else "pending_shared_scoring"
                        ), "details": {
                            "x": str(best_x),
                            "score_forced_to_zero": suppress,
                        }},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=suppress,
                )
            )
        return results
