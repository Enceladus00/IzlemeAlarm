from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R13Values
from backend.detection.rules.common import calendar_window_start
from backend.models import Customer, Transaction


class LayeringChainRule(RuleStrategy):
    definition = RuleDefinition(
        code="R13",
        name="Katmanlama zinciri",
        description="Kısa aralıklarla ve azalan tutarlarla aktarılan aynı para birimli dış transfer zincirlerini bulur.",
        steps=(
            "Son pencere işlemlerinden nakit hesapları ve aynı müşteri içi transferleri çıkar.",
            "Zaman, adım aralığı, para birimi ve tutar azalması koşullarını sağlayan zincirleri ara.",
            "Her zincirdeki hesap sahiplerine en uzun zincir boyunu sigmoid ile puanla.",
        ),
        alert_mode="ALERT",
        parameter_model=R13Values,
        parameters=(
            ParameterSpec("window_days", "integer", "days", "Calendar-day network lookback.", True),
            ParameterSpec("max_step_hours", "integer", "hours", "Maximum time between adjacent chain transactions.", True),
            ParameterSpec("decay_low", "decimal", "ratio", "Inclusive minimum next-amount / prior-amount ratio.", True),
            ParameterSpec("decay_high", "decimal", "ratio", "Inclusive maximum next-amount / prior-amount ratio.", True),
            ParameterSpec("max_depth", "integer", "transactions", "Maximum transaction count in a chain; capped at 20.", True),
            ParameterSpec("cash_accounts", "account ID list", "account_id", "Accounts excluded as cash/custody nodes.", False),
            ParameterSpec("x_esik", "integer", "chain length", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "integer", "chain length", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "This is a network-wide graph search; runtime can grow quickly with dense transaction graphs. The configured max_depth is capped at 20, but transaction volume should still be monitored.",
            "Each customer type's configured bounds are applied to that type's score over the same global active-transaction graph.",
        ),
        feasibility="LOW",
        feasibility_reason="Network path enumeration can become expensive on dense transaction graphs even with a bounded path depth.",
    )

    def evaluate_raw(
        self,
        customers: list[Customer],
        transactions: list[Transaction],
        parameter_sets: dict[str, dict[str, Any]],
        *,
        as_of: datetime,
    ) -> list[RawRuleResult]:
        if not customers:
            return []
        values = parameter_sets[customers[0].customer_type]["values"]
        start = calendar_window_start(as_of, int(values["window_days"]))
        cash_accounts = set(values["cash_accounts"])
        eligible = [
            tx
            for tx in transactions
            if start <= tx.tx_time < as_of
            and tx.sender_account_id not in cash_accounts
            and tx.receiver_account_id not in cash_accounts
            and tx.sender_account.customer_id != tx.receiver_account.customer_id
        ]
        outgoing: dict[int, list[Transaction]] = defaultdict(list)
        owner_by_account: dict[int, int] = {}
        for tx in eligible:
            outgoing[tx.sender_account_id].append(tx)
            owner_by_account[tx.sender_account_id] = tx.sender_account.customer_id
            owner_by_account[tx.receiver_account_id] = tx.receiver_account.customer_id
        for txs in outgoing.values():
            txs.sort(key=lambda tx: (tx.tx_time, tx.transaction_id))

        best_depth: dict[int, int] = defaultdict(int)
        best_chain: dict[int, list[Transaction]] = {}
        max_depth = int(values["max_depth"])
        max_gap = int(values["max_step_hours"])
        decay_low = Decimal(str(values["decay_low"]))
        decay_high = Decimal(str(values["decay_high"]))

        def walk(path: list[Transaction], visited_accounts: set[int]) -> None:
            if not path:
                return
            participant_ids = {
                owner_by_account[account_id]
                for tx in path
                for account_id in (tx.sender_account_id, tx.receiver_account_id)
            }
            for owner_id in participant_ids:
                if len(path) > best_depth[owner_id]:
                    best_depth[owner_id] = len(path)
                    best_chain[owner_id] = list(path)
            if len(path) >= max_depth:
                return
            previous = path[-1]
            for candidate in outgoing.get(previous.receiver_account_id, []):
                gap = candidate.tx_time - previous.tx_time
                if (
                    gap.total_seconds() <= 0
                    or gap.total_seconds() > max_gap * 3600
                ):
                    continue
                if candidate.receiver_account_id in visited_accounts:
                    continue
                if candidate.currency != previous.currency:
                    continue
                ratio = candidate.amount / previous.amount
                if decay_low <= ratio <= decay_high:
                    walk(
                        [*path, candidate],
                        visited_accounts | {candidate.receiver_account_id},
                    )

        for transaction in eligible:
            walk(
                [transaction],
                {transaction.sender_account_id, transaction.receiver_account_id},
            )

        results = []
        for customer in customers:
            values = parameter_sets[customer.customer_type]["values"]
            x = Decimal(best_depth[customer.customer_id])
            evidence = best_chain.get(customer.customer_id, [])
            suppress = not evidence
            results.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=x,
                    transactions=evidence,
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "window_start": start.isoformat(),
                            "eligible_transaction_count": len(eligible),
                            "cash_accounts": sorted(cash_accounts),
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "max_step_hours": max_gap,
                            "decay_low": str(decay_low),
                            "decay_high": str(decay_high),
                            "max_depth": max_depth,
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": (
                            "blocked" if suppress else "pending_shared_scoring"
                        ), "details": {
                            "longest_chain_length": int(x),
                            "evidence_transaction_ids": [
                                tx.transaction_id for tx in evidence
                            ],
                            "score_forced_to_zero": suppress,
                        }},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=suppress,
                )
            )
        return results
