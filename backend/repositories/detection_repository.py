from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from backend.detection.evidence import DetectionEvidence
from backend.models import (
    Account,
    Alert,
    AlertTransaction,
    MonitoringRule,
    Transaction,
)


class SqlAlchemyDetectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_active_rules(self) -> list[MonitoringRule]:
        return list(
            self._session.scalars(
                select(MonitoringRule).where(MonitoringRule.is_active)
            )
        )

    def list_active_transactions(self) -> list[Transaction]:
        return list(
            self._session.scalars(
                select(Transaction)
                .where(Transaction.is_active)
                .options(
                    joinedload(Transaction.sender_account).joinedload(Account.customer),
                    joinedload(Transaction.receiver_account).joinedload(Account.customer),
                )
                .order_by(Transaction.tx_time, Transaction.transaction_id)
            ).unique()
        )

    def list_accounts(self) -> list[Account]:
        return list(
            self._session.scalars(
                select(Account).options(joinedload(Account.customer))
            )
        )

    def create_alerts(
        self,
        candidates: list[DetectionEvidence],
        rules_by_code: dict[str, MonitoringRule],
    ) -> int:
        created = 0
        for candidate in candidates:
            rule = rules_by_code[candidate.rule_code]
            alert_id = self._session.execute(
                insert(Alert)
                .values(
                    rule_id=rule.rule_id,
                    customer_id=candidate.customer_id,
                    severity=(
                        "high" if candidate.rule_code in {"R3", "R4"} else "medium"
                    ),
                    deduplication_key=candidate.deduplication_key,
                )
                .on_conflict_do_nothing(
                    index_elements=[Alert.deduplication_key]
                )
                .returning(Alert.alert_id)
            ).scalar_one_or_none()
            if alert_id is None:
                continue
            self._session.add_all(
                AlertTransaction(
                    alert_id=alert_id,
                    transaction_id=transaction.transaction_id,
                )
                for transaction in candidate.transactions
            )
            created += 1
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return created
