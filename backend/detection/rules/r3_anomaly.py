from collections import defaultdict
from decimal import Decimal

from backend.detection.base import DetectionRepository
from backend.detection.evidence import DetectionEvidence
from backend.models import Transaction


class UnusualAmountStrategy:
    rule_code = "R3"

    def detect(
        self,
        transactions: list[Transaction],
        thresholds: dict[str, object],
        repository: DetectionRepository,
    ) -> list[DetectionEvidence]:
        multiplier = Decimal(str(thresholds.get("average_multiplier", 3)))
        history_count = int(thresholds.get("minimum_history_count", 5))
        grouped: dict[tuple[int, str], list[Transaction]] = defaultdict(list)
        for transaction in transactions:
            grouped[
                (transaction.sender_account.customer_id, transaction.currency)
            ].append(transaction)

        candidates: list[DetectionEvidence] = []
        for (customer_id, _currency), group in grouped.items():
            for index, transaction in enumerate(group):
                previous = group[:index]
                if len(previous) >= history_count:
                    history = previous[-history_count:]
                    average = sum(
                        (item.amount for item in history), Decimal("0")
                    ) / history_count
                    if transaction.amount > average * multiplier:
                        candidates.append(
                            DetectionEvidence(self.rule_code, customer_id, [transaction])
                        )
        return candidates
