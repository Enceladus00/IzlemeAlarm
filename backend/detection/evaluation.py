from dataclasses import dataclass

from backend.detection.metadata import RuleResultEvidence


@dataclass(frozen=True)
class DetectionEvaluation:
    results: list[RuleResultEvidence]
    summary: dict[str, object]
