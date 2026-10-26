from sqlalchemy.orm import Session

from backend.detection.base import RuleStrategy
from backend.detection.engine import DetectionEngine
from backend.detection.rules.r1_threshold import NearThresholdStrategy
from backend.detection.rules.r2_in_out import RapidOutflowStrategy
from backend.detection.rules.r3_anomaly import UnusualAmountStrategy
from backend.detection.rules.r4_country import RiskyCountryStrategy
from backend.repositories.detection_repository import SqlAlchemyDetectionRepository


class DetectionService:
    def __init__(
        self,
        repository: SqlAlchemyDetectionRepository,
        strategies: tuple[RuleStrategy, ...] | None = None,
    ) -> None:
        self._repository = repository
        self._engine = DetectionEngine(
            strategies
            or (
                NearThresholdStrategy(),
                RapidOutflowStrategy(),
                UnusualAmountStrategy(),
                RiskyCountryStrategy(),
            )
        )

    def evaluate(
        self,
        *,
        actor_id: int | None = None,
        automatic: bool = False,
    ) -> int:
        rules = self._repository.list_active_rules()
        rules_by_code = {rule.rule_code: rule for rule in rules}
        transactions = self._repository.list_active_transactions()
        evaluation = self._engine.evaluate(
            transactions,
            rules_by_code,
            self._repository,
        )
        return self._repository.create_alerts(
            evaluation.evidence,
            rules_by_code,
            actor_id=actor_id,
            automatic=automatic,
        )


def evaluate_rules(db: Session) -> int:
    return DetectionService(SqlAlchemyDetectionRepository(db)).evaluate()
