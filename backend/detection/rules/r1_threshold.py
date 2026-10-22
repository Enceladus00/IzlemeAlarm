from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from backend.detection.base import DetectionRepository
from backend.detection.evidence import DetectionEvidence
from backend.models import Transaction


class NearThresholdStrategy:
    rule_code = "R1"

    def detect(
        self,
        transactions: list[Transaction],
        thresholds: dict[str, object],
        repository: DetectionRepository,
    ) -> list[DetectionEvidence]:
        limit = Decimal(str(thresholds.get("amount_limit", 10_000)))
        lower = limit * (
            Decimal("1") - Decimal(str(thresholds.get("proximity_percent", 10))) / 100
        )
        count = int(thresholds.get("transaction_count", 2))
        window = timedelta(minutes=int(thresholds.get("window_minutes", 60)))
        grouped: dict[tuple[int, str], list[Transaction]] = defaultdict(list)
        for transaction in transactions:
            if lower <= transaction.amount < limit:
                grouped[
                    (transaction.sender_account.customer_id, transaction.currency)
                ].append(transaction)

        candidates: list[DetectionEvidence] = []
        for (customer_id, _currency), group in grouped.items():
            start = 0
            while start < len(group):
                first = group[start]
                matching = [
                    transaction
                    for transaction in group[start:]
                    if transaction.tx_time <= first.tx_time + window
                ]
                if len(matching) >= count:
                    candidates.append(
                        DetectionEvidence(self.rule_code, customer_id, matching)
                    )
                    start += len(matching)
                else:
                    start += 1
        return candidates
