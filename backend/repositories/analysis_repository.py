from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    Account,
    Alert,
    AlertTransaction,
    Customer,
    MonitoringRule,
    Transaction,
)


class SqlAlchemyAnalysisRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def check_database(self) -> None:
        self._session.execute(select(1))

    def dashboard_data(
        self,
        trend_start: datetime,
        trend_end: datetime,
    ) -> dict[str, Any]:
        totals = {
            "customers": self._session.scalar(
                select(func.count()).select_from(Customer).where(Customer.is_active)
            ),
            "accounts": self._session.scalar(
                select(func.count()).select_from(Account).where(Account.is_active)
            ),
            "transactions": self._session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.is_active)
            ),
            "alerts": self._session.scalar(select(func.count()).select_from(Alert)),
            "suspicious_transactions": self._session.scalar(
                select(func.count(func.distinct(AlertTransaction.transaction_id)))
                .select_from(AlertTransaction)
            ),
        }
        statuses = self._session.execute(
            select(Alert.status, func.count()).group_by(Alert.status)
        ).all()
        severities = self._session.execute(
            select(Alert.severity, func.count()).group_by(Alert.severity)
        ).all()
        rules = self._session.execute(
            select(MonitoringRule.rule_code, func.count(Alert.alert_id))
            .outerjoin(Alert, Alert.rule_id == MonitoringRule.rule_id)
            .group_by(MonitoringRule.rule_code)
            .order_by(MonitoringRule.rule_code)
        ).all()
        alert_trends = self._session.execute(
            select(func.date(Alert.created_at), func.count())
            .where(Alert.created_at >= trend_start, Alert.created_at < trend_end)
            .group_by(func.date(Alert.created_at))
        ).all()
        suspicious_trends = self._session.execute(
            select(
                func.date(Alert.created_at),
                func.count(func.distinct(AlertTransaction.transaction_id)),
            )
            .join(AlertTransaction, AlertTransaction.alert_id == Alert.alert_id)
            .where(Alert.created_at >= trend_start, Alert.created_at < trend_end)
            .group_by(func.date(Alert.created_at))
        ).all()
        return {
            "totals": totals,
            "statuses": statuses,
            "severities": severities,
            "rules": rules,
            "alert_trends": alert_trends,
            "suspicious_trends": suspicious_trends,
        }
