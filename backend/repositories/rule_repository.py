from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models import AuditLog, MonitoringRule, RuleChangeLog
from backend.repositories.user_repository import SqlAlchemyUserRepository


class SqlAlchemyRuleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._users = SqlAlchemyUserRepository(session)

    def list_rules(self) -> list[MonitoringRule]:
        return list(
            self._session.scalars(
                select(MonitoringRule).order_by(MonitoringRule.rule_code)
            )
        )

    def get_rule(self, rule_code: str) -> MonitoringRule | None:
        return self._session.scalar(
            select(MonitoringRule).where(
                MonitoringRule.rule_code == rule_code.upper()
            )
        )

    def save_rule(
        self,
        rule: MonitoringRule,
        thresholds: dict[str, Any],
        is_active: bool,
    ) -> None:
        user_id = self._users.get_or_create_system_user_id()
        old_thresholds = dict(rule.thresholds)
        rule.thresholds = thresholds
        rule.is_active = is_active
        rule.updated_by = user_id
        rule.updated_at = datetime.now()
        self._session.add(
            RuleChangeLog(
                rule_id=rule.rule_id,
                changed_by=user_id,
                old_thresholds=old_thresholds,
                new_thresholds=thresholds,
            )
        )
        self._session.add(
            AuditLog(
                actor_id=user_id,
                action="rule.updated",
                entity_type="monitoring_rule",
                entity_id=rule.rule_code,
                details={
                    "old_thresholds": old_thresholds,
                    "new_thresholds": thresholds,
                    "is_active": is_active,
                },
            )
        )
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
