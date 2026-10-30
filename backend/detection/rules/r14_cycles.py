from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.detection.metadata import ParameterSpec, RawRuleResult, RuleDefinition, RuleStrategy
from backend.detection.parameters import R14Values
from backend.detection.rules.common import calendar_window_start
from backend.detection.scoring import calculate_score
from backend.models import Customer, Transaction


class CyclePingPongRule(RuleStrategy):
    definition = RuleDefinition(
        code="R14",
        name="Döngü ve ping-pong",
        description="Dış transfer grafiğinde geri dönen tutarlı yolları ve benzer tutarlı ikili hareketleri bulur.",
        steps=(
            "Son pencere işlemlerinden nakit hesapları ve aynı müşteri içi transferleri çıkar.",
            "Aynı para biriminde, zaman sıralı ve tutarı koruyan en kısa üç işlemli döngüleri ara.",
            "Karşılıklı A→B ve sonraki B→A transfer çiftlerini toleransa göre say.",
            "Döngü skoruyla ping-pong skorunun büyüğünü kullan.",
        ),
        alert_mode="ALERT",
        parameter_model=R14Values,
        parameters=(
            ParameterSpec("window_days", "integer", "days", "Calendar-day network lookback.", True),
            ParameterSpec("max_cycle_length", "integer", "transactions", "Maximum cycle path length; 3 to 20.", True),
            ParameterSpec("min_retained", "decimal", "ratio", "Minimum last amount / first amount for a cycle.", True),
            ParameterSpec("pingpong_tolerance", "decimal", "relative difference", "Maximum relative difference between forward and reverse amounts.", True),
            ParameterSpec("cash_accounts", "account ID list", "account_id", "Accounts excluded as cash/custody nodes.", False),
            ParameterSpec("x_esik", "integer", "ping-pong pairs", "Score anchor at 0.5.", True),
            ParameterSpec("x_kesin", "integer", "ping-pong pairs", "Score anchor at 0.9.", True),
        ),
        analyst_review_notes=(
            "Cycle search is bounded by max_cycle_length (at most 20), but dense network graphs can still create many candidate paths.",
            "Currency is held constant through a cycle or ping-pong pair so amount ratios are meaningful without FX data.",
        ),
        feasibility="LOW",
        feasibility_reason="Cycle enumeration can become expensive on dense graphs and needs representative performance/calibration data.",
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
        owner_by_account: dict[int, int] = {}
        outgoing: dict[int, list[Transaction]] = defaultdict(list)
        pair_transactions: dict[tuple[int, int, str], list[Transaction]] = defaultdict(list)
        for tx in eligible:
            owner_by_account[tx.sender_account_id] = tx.sender_account.customer_id
            owner_by_account[tx.receiver_account_id] = tx.receiver_account.customer_id
            outgoing[tx.sender_account_id].append(tx)
            pair_transactions[
                (tx.sender_account_id, tx.receiver_account_id, tx.currency)
            ].append(tx)
        for txs in outgoing.values():
            txs.sort(key=lambda tx: (tx.tx_time, tx.transaction_id))
        for txs in pair_transactions.values():
            txs.sort(key=lambda tx: (tx.tx_time, tx.transaction_id))
        cycle_evidence: dict[int, list[Transaction]] = {}
        max_length = int(values["max_cycle_length"])
        min_retained = Decimal(str(values["min_retained"]))

        def walk(
            path: list[Transaction],
            visited_transactions: set[int],
            visited_accounts: set[int],
        ) -> None:
            last = path[-1]
            if (
                len(path) >= 3
                and last.receiver_account_id == path[0].sender_account_id
                and last.currency == path[0].currency
                and last.amount / path[0].amount >= min_retained
            ):
                owners = {
                    owner_by_account[account_id]
                    for tx in path
                    for account_id in (tx.sender_account_id, tx.receiver_account_id)
                }
                for owner in owners:
                    if len(path) > len(cycle_evidence.get(owner, [])):
                        cycle_evidence[owner] = list(path)
                return
            if len(path) >= max_length:
                return
            for candidate in outgoing.get(last.receiver_account_id, []):
                if candidate.transaction_id in visited_transactions:
                    continue
                if candidate.tx_time <= last.tx_time or candidate.currency != last.currency:
                    continue
                if (
                    candidate.receiver_account_id in visited_accounts
                    and candidate.receiver_account_id != path[0].sender_account_id
                ):
                    continue
                walk(
                    [*path, candidate],
                    visited_transactions | {candidate.transaction_id},
                    visited_accounts | {candidate.receiver_account_id},
                )

        for tx in eligible:
            walk(
                [tx],
                {tx.transaction_id},
                {tx.sender_account_id, tx.receiver_account_id},
            )

        pingpong_count: dict[int, int] = defaultdict(int)
        pingpong_evidence: dict[int, list[Transaction]] = defaultdict(list)
        counted_pairs: set[tuple[int, int]] = set()
        tolerance = Decimal(str(values["pingpong_tolerance"]))
        for (sender_id, receiver_id, currency), forward_txs in pair_transactions.items():
            reverse_txs = pair_transactions.get((receiver_id, sender_id, currency), [])
            used_reverse: set[int] = set()
            for forward in forward_txs:
                reverse = next(
                    (
                        tx
                        for tx in reverse_txs
                        if tx.transaction_id not in used_reverse
                        and tx.tx_time > forward.tx_time
                        and tuple(
                            sorted((forward.transaction_id, tx.transaction_id))
                        )
                        not in counted_pairs
                        and abs(forward.amount - tx.amount)
                        / max(forward.amount, tx.amount)
                        <= tolerance
                    ),
                    None,
                )
                if reverse is None:
                    continue
                used_reverse.add(reverse.transaction_id)
                counted_pairs.add(
                    tuple(sorted((forward.transaction_id, reverse.transaction_id)))
                )
                owners = {
                    owner_by_account[sender_id],
                    owner_by_account[receiver_id],
                }
                for owner in owners:
                    pingpong_count[owner] += 1
                    pingpong_evidence[owner].extend([forward, reverse])

        results = []
        for customer in customers:
            values = parameter_sets[customer.customer_type]["values"]
            cycles = cycle_evidence.get(customer.customer_id, [])
            pairs = pingpong_count[customer.customer_id]
            pingpong_score = (
                calculate_score(
                    Decimal(pairs),
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                )
                if pairs
                else Decimal("0")
            )
            cycle_score = Decimal("1") if cycles else Decimal("0")
            evidence_by_id = {
                tx.transaction_id: tx
                for tx in (cycles or pingpong_evidence[customer.customer_id])
            }
            evidence = list(evidence_by_id.values())
            score = max(cycle_score, pingpong_score)
            x = Decimal(len(cycles)) if cycles else Decimal(pairs)
            suppress = score == 0
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
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "cycle_length_limit": max_length,
                            "minimum_retained": str(min_retained),
                            "cycle_transaction_ids": [tx.transaction_id for tx in cycles],
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": "completed", "details": {
                            "pingpong_pair_count": pairs,
                            "pingpong_transaction_ids": [
                                tx.transaction_id
                                for tx in pingpong_evidence[customer.customer_id]
                            ],
                        }},
                        {"step": 4, "text": self.definition.steps[3], "status": (
                            "blocked" if suppress else "completed"
                        ), "details": {
                            "cycle_score": str(cycle_score),
                            "pingpong_score": str(pingpong_score),
                            "score": str(score),
                        }},
                    ],
                    x_esik=Decimal(str(values["x_esik"])),
                    x_kesin=Decimal(str(values["x_kesin"])),
                    force_zero=suppress,
                    score_override=score,
                )
            )
        return results
