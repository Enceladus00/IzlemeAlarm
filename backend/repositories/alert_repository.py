from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.models import (
    Account,
    Alert,
    AlertStatusHistory,
    AlertTransaction,
    AuditLog,
    MonitoringRule,
    Transaction,
)
from backend.repositories.user_repository import SqlAlchemyUserRepository


class SqlAlchemyAlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._users = SqlAlchemyUserRepository(session)

    def list_alerts(
        self,
        *,
        status: str | None,
        severity: str | None,
        rule_code: str | None,
        date_from: date | None,
        date_to: date | None,
        offset: int,
        limit: int,
    ) -> tuple[int, list[Alert]]:
        query = (
            select(Alert)
            .join(Alert.customer)
            .join(Alert.rule)
            .options(
                joinedload(Alert.customer),
                joinedload(Alert.rule),
                selectinload(Alert.transactions),
            )
        )
        if status:
            query = query.where(Alert.status == status)
        if severity:
            query = query.where(Alert.severity == severity)
        if rule_code:
            query = query.where(MonitoringRule.rule_code == rule_code)
        if date_from:
            query = query.where(
                Alert.created_at >= datetime.combine(date_from, time.min)
            )
        if date_to:
            query = query.where(
                Alert.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
            )
        total = int(
            self._session.scalar(select(func.count()).select_from(query.subquery()))
            or 0
        )
        alerts = list(
            self._session.scalars(
                query.order_by(Alert.created_at.desc(), Alert.alert_id.desc())
                .offset(offset)
                .limit(limit)
            ).unique()
        )
        return total, alerts

    def get_alert(self, alert_id: int) -> Alert | None:
        return self._session.scalar(
            select(Alert)
            .where(Alert.alert_id == alert_id)
            .options(
                joinedload(Alert.customer),
                joinedload(Alert.rule),
                selectinload(Alert.transactions)
                .joinedload(AlertTransaction.transaction)
                .joinedload(Transaction.sender_account)
                .joinedload(Account.customer),
                selectinload(Alert.transactions)
                .joinedload(AlertTransaction.transaction)
                .joinedload(Transaction.receiver_account)
                .joinedload(Account.customer),
                selectinload(Alert.history),
            )
        )

    def get_alert_status(self, alert_id: int) -> Alert | None:
        return self._session.get(Alert, alert_id)

    def save_status_event(
        self,
        alert: Alert,
        new_status: str,
        note: str | None,
    ) -> None:
        user_id = self._users.get_or_create_system_user_id()
        old_status = alert.status
        self._session.add(
            AlertStatusHistory(
                alert_id=alert.alert_id,
                changed_by=user_id,
                old_status=old_status,
                new_status=new_status,
                note=note,
            )
        )
        self._session.add(
            AuditLog(
                actor_id=user_id,
                action=(
                    "alert.note_added" if old_status == new_status
                    else "alert.status_changed"
                ),
                entity_type="alert",
                entity_id=str(alert.alert_id),
                details={
                    "old_status": old_status,
                    "new_status": new_status,
                    "note": note,
                },
            )
        )
        alert.status = new_status
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise


def alert_summary(alert: Alert) -> dict[str, Any]:
    return {
        "alert_id": alert.alert_id,
        "rule_code": alert.rule.rule_code,
        "rule_name": alert.rule.name,
        "customer_no": alert.customer.customer_no,
        "customer_name": alert.customer.full_name,
        "severity": alert.severity,
        "status": alert.status,
        "created_at": alert.created_at,
        "transaction_count": len(alert.transactions),
        "transaction_ids": [
            relation.transaction_id for relation in alert.transactions
        ],
    }
