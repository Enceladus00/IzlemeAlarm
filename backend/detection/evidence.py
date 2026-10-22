from dataclasses import dataclass
from hashlib import sha256

from backend.models import Transaction


@dataclass(frozen=True)
class DetectionEvidence:
    rule_code: str
    customer_id: int
    transactions: list[Transaction]
    scope_id: int | None = None

    @property
    def deduplication_key(self) -> str:
        return deduplication_key(
            self.rule_code,
            self.transactions,
            self.scope_id,
        )


def deduplication_key(
    rule_code: str,
    transactions: list[Transaction],
    scope_id: int | None = None,
) -> str:
    transaction_ids = sorted(transaction.transaction_id for transaction in transactions)
    digest = sha256(
        f"{scope_id or ''}:{','.join(map(str, transaction_ids))}".encode()
    ).hexdigest()
    return f"{rule_code}:{digest}"
