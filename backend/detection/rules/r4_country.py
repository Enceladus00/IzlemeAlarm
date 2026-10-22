from backend.detection.base import DetectionRepository
from backend.detection.evidence import DetectionEvidence
from backend.models import Transaction


class RiskyCountryStrategy:
    rule_code = "R4"

    def detect(
        self,
        transactions: list[Transaction],
        thresholds: dict[str, object],
        repository: DetectionRepository,
    ) -> list[DetectionEvidence]:
        if not thresholds.get("enabled"):
            return []
        countries = {
            str(country).upper()
            for country in thresholds.get("countries", [])
        }
        return [
            DetectionEvidence(
                self.rule_code,
                transaction.sender_account.customer_id,
                [transaction],
            )
            for transaction in transactions
            if transaction.country_code in countries
        ]
