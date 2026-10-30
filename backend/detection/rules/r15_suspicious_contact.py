from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.detection.metadata import (
    DetectionContext,
    ParameterSpec,
    RawRuleResult,
    RuleDefinition,
    RuleStrategy,
)
from backend.detection.parameters import R15Values
from backend.detection.rules.common import calendar_window_start
from backend.models import Customer, Transaction


class SuspiciousContactRule(RuleStrategy):
    definition = RuleDefinition(
        code="R15",
        name="Şüpheli hesapla temas",
        description="Daha önce şüpheli olduğu onaylanan hesaplarla doğrudan veya tek aracı üzerinden temasları bulur.",
        steps=(
            "Seçili geçmiş durumuna geçmiş müşterilerin hesaplarını belirle.",
            "Aday müşterilerin son dönem dış hesap temas ağını nakit hesapları hariç kur.",
            "Şüpheli hesaba doğrudan veya tek aracı üzerinden erişimi bul.",
            "Doğrudan temasa 1, iki adımlı temasa gamma skorunu ata.",
        ),
        alert_mode="ALERT",
        parameter_model=R15Values,
        parameters=(
            ParameterSpec("window_days", "integer", "days", "Calendar-day contact lookback.", True),
            ParameterSpec("suspicious_status", "status", "alert status", "Alert-history status proving a confirmed-suspicious customer.", True),
            ParameterSpec("gamma", "decimal", "score", "Score for contact through exactly one intermediary.", True),
            ParameterSpec("cash_accounts", "account ID list", "account_id", "Accounts excluded from contact paths.", False),
        ),
        analyst_review_notes=(
            "The specification's path description is implemented as a two-hop account graph. Intermediate nodes are not recursively expanded beyond one intermediary.",
            "Only the existing confirmed_suspicious status is supported. A historical status event remains qualifying even if the alert was later moved to another status.",
        ),
        feasibility="MEDIUM",
        feasibility_reason="Requires alert-status history and account ownership, both present; configured account exclusions and two-hop interpretation need analyst review.",
    )

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: datetime,
        context: DetectionContext | None = None,
    ) -> list[RawRuleResult]:
        results = []
        suspicious_by_status = (
            context.suspicious_customer_ids_by_status if context else {}
        )
        account_owner: dict[int, int] = {}
        for tx in transactions:
            account_owner[tx.sender_account_id] = tx.sender_account.customer_id
            account_owner[tx.receiver_account_id] = tx.receiver_account.customer_id
        for customer in customers:
            values = parameter_sets[customer.customer_type]["values"]
            status = values["suspicious_status"]
            suspicious_customers = suspicious_by_status.get(status, set())
            suspicious_accounts = context.suspicious_account_ids_by_status.get(
                status, set()
            ) if context else {
                account_id
                for account_id, owner_id in account_owner.items()
                if owner_id in suspicious_customers
            }
            customer_accounts = {
                account.account_id for account in customer.accounts if account.is_active
            }
            cash_accounts = set(values["cash_accounts"])
            start = calendar_window_start(as_of, int(values["window_days"]))
            if customer.customer_id in suspicious_customers:
                direct_evidence: list[Transaction] = []
                second_evidence: list[Transaction] = []
            else:
                graph: dict[int, list[tuple[int, Transaction]]] = defaultdict(list)
                direct_evidence = []
                for tx in transactions:
                    if not start <= tx.tx_time < as_of:
                        continue
                    if (
                        tx.sender_account_id in cash_accounts
                        or tx.receiver_account_id in cash_accounts
                        or tx.sender_account.customer_id == tx.receiver_account.customer_id
                    ):
                        continue
                    graph[tx.sender_account_id].append(
                        (tx.receiver_account_id, tx)
                    )
                    graph[tx.receiver_account_id].append(
                        (tx.sender_account_id, tx)
                    )
                    if (
                        tx.sender_account_id in customer_accounts
                        and tx.receiver_account_id in suspicious_accounts
                    ) or (
                        tx.receiver_account_id in customer_accounts
                        and tx.sender_account_id in suspicious_accounts
                    ):
                        direct_evidence.append(tx)
                second_evidence = []
                if not direct_evidence:
                    for own_account in customer_accounts:
                        for neighbor, first_tx in graph.get(own_account, []):
                            for second_neighbor, second_tx in graph.get(neighbor, []):
                                if (
                                    second_neighbor in suspicious_accounts
                                    and second_neighbor not in customer_accounts
                                    and first_tx.transaction_id != second_tx.transaction_id
                                ):
                                    second_evidence.extend([first_tx, second_tx])
                second_evidence = list(
                    {tx.transaction_id: tx for tx in second_evidence}.values()
                )
            if direct_evidence:
                score = Decimal("1")
                evidence = direct_evidence
                h = 1
            elif second_evidence:
                score = Decimal(str(values["gamma"]))
                evidence = second_evidence
                h = 2
            else:
                score = Decimal("0")
                evidence = []
                h = 0
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=Decimal(h),
                    transactions=evidence,
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "suspicious_status": status,
                            "suspicious_customer_count": len(suspicious_customers),
                            "suspicious_account_count": len(suspicious_accounts),
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "window_start": start.isoformat(),
                            "cash_accounts": sorted(cash_accounts),
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": "completed", "details": {
                            "contact_depth": h,
                            "evidence_transaction_ids": [
                                tx.transaction_id for tx in evidence
                            ],
                            "self_suspicious_customer_skipped": (
                                customer.customer_id in suspicious_customers
                            ),
                        }},
                        {"step": 4, "text": self.definition.steps[3], "status": "completed", "details": {
                            "gamma": str(values["gamma"]),
                            "score": str(score),
                        }},
                    ],
                    score_override=score,
                    force_zero=score == 0,
                )
            )
        return results
