from collections.abc import Iterable

from backend.detection.base import DetectionRepository, RuleStrategy
from backend.detection.evaluation import DetectionEvaluation
from backend.models import MonitoringRule, Transaction


class DetectionEngine:
    def __init__(self, strategies: Iterable[RuleStrategy]) -> None:
        self._strategies = tuple(strategies)

    def evaluate(
        self,
        transactions: list[Transaction],
        rules_by_code: dict[str, MonitoringRule],
        repository: DetectionRepository,
    ) -> DetectionEvaluation:
        evidence = []
        for strategy in self._strategies:
            rule = rules_by_code.get(strategy.rule_code)
            if rule is not None:
                evidence.extend(
                    strategy.detect(transactions, rule.thresholds, repository)
                )
        return DetectionEvaluation(evidence)
