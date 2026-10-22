"""Backward-compatible imports for the original detection entry points."""

from backend.detection.evidence import deduplication_key
from backend.services.detection_service import evaluate_rules
from backend.models import Transaction


def _dedup(
    rule_code: str,
    transactions: list[Transaction],
    scope_id: int | None = None,
) -> str:
    return deduplication_key(rule_code, transactions, scope_id)


__all__ = ["_dedup", "evaluate_rules"]
