from dataclasses import dataclass

from backend.detection.evidence import DetectionEvidence


@dataclass(frozen=True)
class DetectionEvaluation:
    evidence: list[DetectionEvidence]

    @property
    def alert_count(self) -> int:
        return len(self.evidence)
