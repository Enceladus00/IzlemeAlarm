import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.detection.engine import DetectionEngine
from backend.repositories.detection_repository import SqlAlchemyDetectionRepository


logger = logging.getLogger(__name__)


class DetectionService:
    def __init__(
        self,
        repository: SqlAlchemyDetectionRepository,
        engine: DetectionEngine | None = None,
    ) -> None:
        self._repository = repository
        self._engine = engine or DetectionEngine()

    def evaluate(
        self,
        *,
        actor_id: int | None = None,
        automatic: bool = False,
        as_of: datetime | None = None,
        customer_ids: set[int] | None = None,
        rule_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> int:
        run_as_of = as_of or datetime.now()
        rules = self._repository.list_rules()
        rules_by_code = {rule.rule_code: rule for rule in rules}
        customers = self._repository.list_active_customers(customer_ids)
        transactions = self._repository.list_active_transactions()
        evaluation = self._engine.evaluate(
            customers,
            transactions,
            rules_by_code,
            as_of=run_as_of,
            rule_overrides=rule_overrides,
        )
        created = self._repository.persist_run(
            uuid4(),
            run_as_of,
            evaluation,
            rules_by_code,
            actor_id=actor_id,
            automatic=automatic,
        )
        logger.info("Detection run completed: %s", evaluation.summary)
        return created


def evaluate_rules(db: Session) -> int:
    return DetectionService(SqlAlchemyDetectionRepository(db)).evaluate()
