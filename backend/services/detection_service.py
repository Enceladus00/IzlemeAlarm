import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from backend.detection.engine import DetectionEngine
from backend.detection.evaluation import DetectionEvaluation
from backend.detection.metadata import DetectionContext
from backend.repositories.detection_repository import SqlAlchemyDetectionRepository


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectionRunOutcome:
    run_id: UUID
    created_alerts: int
    evaluation: DetectionEvaluation


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
        transaction_customer_ids: set[int] | None = None,
        suspicious_customer_ids: set[int] | None = None,
    ) -> int:
        return self._evaluate(
            actor_id=actor_id,
            automatic=automatic,
            as_of=as_of,
            customer_ids=customer_ids,
            rule_overrides=rule_overrides,
            transaction_customer_ids=transaction_customer_ids,
            suspicious_customer_ids=suspicious_customer_ids,
        ).created_alerts

    def evaluate_detailed(
        self,
        *,
        actor_id: int | None = None,
        automatic: bool = False,
        as_of: datetime | None = None,
        customer_ids: set[int] | None = None,
        rule_overrides: dict[str, dict[str, Any]] | None = None,
        transaction_customer_ids: set[int] | None = None,
        suspicious_customer_ids: set[int] | None = None,
    ) -> DetectionRunOutcome:
        return self._evaluate(
            actor_id=actor_id,
            automatic=automatic,
            as_of=as_of,
            customer_ids=customer_ids,
            rule_overrides=rule_overrides,
            transaction_customer_ids=transaction_customer_ids,
            suspicious_customer_ids=suspicious_customer_ids,
        )

    def _evaluate(
        self,
        *,
        actor_id: int | None,
        automatic: bool,
        as_of: datetime | None,
        customer_ids: set[int] | None,
        rule_overrides: dict[str, dict[str, Any]] | None,
        transaction_customer_ids: set[int] | None,
        suspicious_customer_ids: set[int] | None,
    ) -> DetectionRunOutcome:
        run_as_of = as_of or datetime.now()
        rules = self._repository.list_rules()
        rules_by_code = {rule.rule_code: rule for rule in rules}
        customers = self._repository.list_active_customers(customer_ids)
        transactions = self._repository.list_active_transactions(
            transaction_customer_ids
        )
        suspicious_status_ids = (
            set(suspicious_customer_ids)
            if suspicious_customer_ids is not None
            else self._repository.list_customers_with_history_status(
                "confirmed_suspicious"
            )
        )
        suspicious_account_ids = self._repository.list_account_ids_for_customers(
            suspicious_status_ids
        )
        context = DetectionContext(
            suspicious_customer_ids_by_status={
                "confirmed_suspicious": suspicious_status_ids
            },
            suspicious_account_ids_by_status={
                "confirmed_suspicious": suspicious_account_ids
            },
        )
        evaluation = self._engine.evaluate(
            customers,
            transactions,
            rules_by_code,
            as_of=run_as_of,
            rule_overrides=rule_overrides,
            context=context,
        )
        run_id = uuid4()
        created = self._repository.persist_run(
            run_id,
            run_as_of,
            evaluation,
            rules_by_code,
            actor_id=actor_id,
            automatic=automatic,
        )
        logger.info("Detection run completed: %s", evaluation.summary)
        return DetectionRunOutcome(run_id, created, evaluation)


def evaluate_rules(db: Session) -> int:
    return DetectionService(SqlAlchemyDetectionRepository(db)).evaluate()
