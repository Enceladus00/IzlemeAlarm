from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased, joinedload, selectinload

from backend.detection.evidence import alert_severity, daily_deduplication_key
from backend.detection.evaluation import DetectionEvaluation
from backend.detection.metadata import RuleResultEvidence
from backend.models import (
    Account,
    Alert,
    AlertTransaction,
    AlertStatusHistory,
    AuditLog,
    Customer,
    DetectionRun,
    MonitoringRule,
    RuleResult,
    RuleResultTransaction,
    Transaction,
)


class SqlAlchemyDetectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_rules(self) -> list[MonitoringRule]:
        return list(
            self._session.scalars(
                select(MonitoringRule).order_by(MonitoringRule.rule_code)
            )
        )

    def list_active_customers(
        self, customer_ids: set[int] | None = None
    ) -> list[Customer]:
        statement = select(Customer).where(Customer.is_active)
        statement = statement.options(selectinload(Customer.accounts))
        if customer_ids is not None:
            if not customer_ids:
                return []
            statement = statement.where(Customer.customer_id.in_(customer_ids))
        return list(
            self._session.scalars(statement.order_by(Customer.customer_id))
        )

    def list_customers_with_history_status(self, status: str) -> set[int]:
        return set(
            self._session.scalars(
                select(Alert.customer_id)
                .join(AlertStatusHistory, AlertStatusHistory.alert_id == Alert.alert_id)
                .where(AlertStatusHistory.new_status == status)
                .distinct()
            )
        )

    def list_account_ids_for_customers(self, customer_ids: set[int]) -> set[int]:
        if not customer_ids:
            return set()
        return set(
            self._session.scalars(
                select(Account.account_id).where(
                    Account.customer_id.in_(customer_ids),
                    Account.is_active,
                )
            )
        )

    def list_active_transactions(
        self, customer_ids: set[int] | None = None
    ) -> list[Transaction]:
        statement = select(Transaction).where(Transaction.is_active)
        if customer_ids is not None:
            if not customer_ids:
                return []
            sender = aliased(Account)
            receiver = aliased(Account)
            statement = (
                statement.join(
                    sender, Transaction.sender_account_id == sender.account_id
                )
                .join(
                    receiver, Transaction.receiver_account_id == receiver.account_id
                )
                .where(
                    sender.customer_id.in_(customer_ids),
                    receiver.customer_id.in_(customer_ids),
                )
            )
        return list(
            self._session.scalars(
                statement
                .options(
                    joinedload(Transaction.sender_account).joinedload(Account.customer),
                    joinedload(Transaction.receiver_account).joinedload(Account.customer),
                )
                .order_by(Transaction.tx_time, Transaction.transaction_id)
            ).unique()
        )

    def persist_run(
        self,
        run_id: UUID,
        as_of: datetime,
        evaluation: DetectionEvaluation,
        rules_by_code: dict[str, MonitoringRule],
        *,
        actor_id: int | None = None,
        automatic: bool = False,
    ) -> int:
        run = DetectionRun(
            run_id=run_id,
            as_of=as_of,
            status="completed",
            completed_at=datetime.now(),
            summary=evaluation.summary,
        )
        self._session.add(run)
        result_pairs: list[tuple[RuleResultEvidence, RuleResult]] = []
        for result in evaluation.results:
            rule = rules_by_code[result.rule_code]
            row = RuleResult(
                run_id=run_id,
                rule_id=rule.rule_id,
                customer_id=result.customer_id,
                customer_type=result.customer_type,
                weight_snapshot=rule.weight,
                parameter_snapshot=result.parameter_snapshot,
                parameter_status=result.parameter_status,
                result_status=result.result_status,
                raw_x=result.raw_x,
                score=result.score,
                alert_mode=result.alert_mode,
                step_trace=result.step_trace,
            )
            result_pairs.append((result, row))
            self._session.add(row)
        self._session.flush()
        self._session.add_all(
            RuleResultTransaction(
                result_id=row.result_id,
                transaction_id=transaction.transaction_id,
            )
            for result, row in result_pairs
            for transaction in result.transactions
        )

        alert_values = []
        transaction_ids_by_key: dict[str, list[int]] = {}
        scores_by_key: dict[str, Decimal] = {}
        for result, _row in result_pairs:
            if (
                result.alert_mode != "ALERT"
                or result.result_status != "evaluated"
                or result.score is None
                or result.score < Decimal("0.5")
            ):
                continue
            key = daily_deduplication_key(
                result.rule_code,
                result.customer_id,
                as_of.date(),
            )
            alert_values.append(
                {
                    "rule_id": rules_by_code[result.rule_code].rule_id,
                    "customer_id": result.customer_id,
                    "severity": alert_severity(result.score),
                    "score": result.score,
                    "deduplication_key": key,
                }
            )
            scores_by_key[key] = result.score
            transaction_ids_by_key[key] = list(dict.fromkeys(
                transaction.transaction_id for transaction in result.transactions
            ))
        created_alerts = []
        if alert_values:
            created_alerts = self._session.execute(
                insert(Alert)
                .values(alert_values)
                .on_conflict_do_nothing(index_elements=[Alert.deduplication_key])
                .returning(Alert.alert_id, Alert.deduplication_key)
            ).all()
        alert_ids_by_key = {
            key: alert_id for alert_id, key in created_alerts
        }
        if transaction_ids_by_key:
            existing_alerts = self._session.scalars(
                select(Alert).where(
                    Alert.deduplication_key.in_(transaction_ids_by_key)
                )
            ).all()
            for alert in existing_alerts:
                key = alert.deduplication_key
                alert_ids_by_key[key] = alert.alert_id
                score = scores_by_key[key]
                if alert.score is None or alert.score < score:
                    alert.score = score
                    alert.severity = alert_severity(score)
        alert_transaction_values = [
            {
                "alert_id": alert_id,
                "transaction_id": transaction_id,
            }
            for key, alert_id in alert_ids_by_key.items()
            for transaction_id in transaction_ids_by_key[key]
        ]
        if alert_transaction_values:
            self._session.execute(
                insert(AlertTransaction)
                .values(alert_transaction_values)
                .on_conflict_do_nothing()
            )

        created = len(created_alerts)
        evaluation.summary["created_alerts"] = created
        run_summary = dict(evaluation.summary)
        run.summary = run_summary
        if actor_id is not None:
            self._session.add(
                AuditLog(
                    actor_id=actor_id,
                    action="detection.auto_run" if automatic else "detection.run",
                    entity_type="detection",
                    details={
                        "run_id": str(run_id),
                        "created_alerts": created,
                        "automatic": automatic,
                        "summary": run_summary,
                    },
                )
            )
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return created
