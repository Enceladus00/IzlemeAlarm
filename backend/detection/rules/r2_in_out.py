from datetime import timedelta
from decimal import Decimal

from backend.detection.base import DetectionRepository
from backend.detection.evidence import DetectionEvidence
from backend.models import Transaction


class RapidOutflowStrategy:
    rule_code = "R2"

    def detect(
        self,
        transactions: list[Transaction],
        thresholds: dict[str, object],
        repository: DetectionRepository,
    ) -> list[DetectionEvidence]:
        ratio = Decimal(str(thresholds.get("outflow_ratio", 0.8)))
        window = timedelta(minutes=int(thresholds.get("window_minutes", 60)))
        candidates: list[DetectionEvidence] = []
        for account in repository.list_accounts():
            relevant = [
                transaction
                for transaction in transactions
                if transaction.currency == account.currency
                and (
                    transaction.sender_account_id == account.account_id
                    or transaction.receiver_account_id == account.account_id
                )
            ]
            for first in relevant:
                matching = [
                    transaction
                    for transaction in relevant
                    if first.tx_time <= transaction.tx_time <= first.tx_time + window
                ]
                incoming = sum(
                    (
                        transaction.amount
                        for transaction in matching
                        if transaction.receiver_account_id == account.account_id
                    ),
                    Decimal("0"),
                )
                outgoing = sum(
                    (
                        transaction.amount
                        for transaction in matching
                        if transaction.sender_account_id == account.account_id
                    ),
                    Decimal("0"),
                )
                if incoming > 0 and outgoing / incoming >= ratio:
                    candidates.append(
                        DetectionEvidence(
                            self.rule_code,
                            account.customer_id,
                            matching,
                            account.account_id,
                        )
                    )
        return candidates
