from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models import AppRole, AppUser, AuditLog, MonitoringRule, RuleChangeLog


class SqlAlchemyRuleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

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

    def rule_history(self, rule_code: str, limit: int) -> list[dict[str, Any]]:
        """E07: the rule's saved changes, newest first, from the audit log
        (the only place that keeps the reason next to the old and new values)."""
        rows = self._session.execute(
            select(
                AuditLog.audit_id,
                AuditLog.created_at,
                AuditLog.details,
                AppUser.username,
                AppRole.role_code,
            )
            .outerjoin(AppUser, AppUser.user_id == AuditLog.actor_id)
            .outerjoin(AppRole, AppRole.role_id == AppUser.role_id)
            .where(
                AuditLog.action == "rule.updated",
                AuditLog.entity_type == "monitoring_rule",
                AuditLog.entity_id == rule_code.upper(),
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
            .limit(limit)
        ).all()
        return [
            {
                "change_id": row.audit_id,
                "changed_at": row.created_at,
                "details": row.details or {},
                "actor_name": row.username,
                "actor_role": row.role_code,
            }
            for row in rows
        ]

    def save_rule(
        self,
        rule: MonitoringRule,
        thresholds: dict[str, Any],
        is_active: bool,
        weight: Any,
        actor_id: int,
        reason: str = "",
    ) -> None:
        old_thresholds = dict(rule.thresholds)
        old_weight = rule.weight
        old_is_active = rule.is_active
        rule.thresholds = thresholds
        rule.is_active = is_active
        rule.weight = weight
        rule.updated_by = actor_id
        rule.updated_at = datetime.now()
        self._session.add(
            RuleChangeLog(
                rule_id=rule.rule_id,
                changed_by=actor_id,
                old_thresholds=old_thresholds,
                new_thresholds=thresholds,
            )
        )
        self._session.add(
            AuditLog(
                actor_id=actor_id,
                action="rule.updated",
                entity_type="monitoring_rule",
                entity_id=rule.rule_code,
                details={
                    "old_thresholds": old_thresholds,
                    "new_thresholds": thresholds,
                    "old_weight": str(old_weight),
                    "new_weight": str(weight),
                    "old_is_active": old_is_active,
                    "new_is_active": is_active,
                    "is_active": is_active,
                    "reason": reason,
                },
            )
        )
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
