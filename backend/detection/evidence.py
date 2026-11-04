from datetime import date
from decimal import Decimal
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


def daily_deduplication_key(rule_code: str, customer_id: int, run_date: date) -> str:
    return f"{rule_code}:{customer_id}:{run_date.isoformat()}"


def alert_severity(score: Decimal) -> str:
    if score >= Decimal("0.9"):
        return "high"
    if score >= Decimal("0.7"):
        return "medium"
    return "low"


SEVERITY_ORDER = ("low", "medium", "high")


def max_severity(first: str, second: str) -> str:
    rank = {name: index for index, name in enumerate(SEVERITY_ORDER)}
    return first if rank.get(first, 0) >= rank.get(second, 0) else second


def raise_severity(severity: str) -> str:
    """One step up (low -> medium -> high); high stays high."""
    index = SEVERITY_ORDER.index(severity) if severity in SEVERITY_ORDER else 0
    return SEVERITY_ORDER[min(index + 1, len(SEVERITY_ORDER) - 1)]
