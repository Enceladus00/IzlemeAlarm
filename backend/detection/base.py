from typing import Protocol

from backend.detection.evidence import DetectionEvidence
from backend.models import Account, Transaction


class DetectionRepository(Protocol):
    def list_accounts(self) -> list[Account]: ...


class RuleStrategy(Protocol):
    rule_code: str

    def detect(
        self,
        transactions: list[Transaction],
        thresholds: dict[str, object],
        repository: DetectionRepository,
    ) -> list[DetectionEvidence]: ...
