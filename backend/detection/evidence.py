from hashlib import sha256

from backend.models import Transaction


def deduplication_key(
    rule_code: str,
    transactions: list[Transaction],
    scope_id: int | None = None,
    *,
    customer_id: int | None = None,
) -> str:
    transaction_ids = sorted(transaction.transaction_id for transaction in transactions)
    digest = sha256(
        f"{customer_id or ''}:{scope_id or ''}:{','.join(map(str, transaction_ids))}".encode()
    ).hexdigest()
    return f"{rule_code}:{digest}"
