from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from backend.models import (
    Account,
    Alert,
    AlertTransaction,
    AppRole,
    AppUser,
    AuditLog,
    Customer,
    DetectionRun,
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

    def system_overview_data(
        self, seven_days_ago: datetime, twenty_four_hours_ago: datetime
    ) -> dict[str, Any]:
        record_metrics = {}
        for key, model, id_column, created_column in (
            ("customers", Customer, Customer.customer_id, Customer.created_at),
            ("accounts", Account, Account.account_id, Account.created_at),
            (
                "transactions",
                Transaction,
                Transaction.transaction_id,
                Transaction.loaded_at,
            ),
            ("alerts", Alert, Alert.alert_id, Alert.created_at),
        ):
            row = self._session.execute(
                select(
                    func.count(id_column),
                    func.coalesce(
                        func.sum(
                            case((created_column >= seven_days_ago, 1), else_=0)
                        ),
                        0,
                    ),
                    func.max(created_column),
                ).select_from(model)
            ).one()
            record_metrics[key] = {
                "total": int(row[0] or 0),
                "added_last_7_days": int(row[1] or 0),
                "last_added_at": row[2],
            }

        audit_counts = dict(
            self._session.execute(
                select(AuditLog.action, func.count())
                .where(
                    AuditLog.created_at >= twenty_four_hours_ago,
                    AuditLog.action.in_(("LOGIN_FAILED", "ACCESS_DENIED")),
                )
                .group_by(AuditLog.action)
            ).all()
        )
        last_run = self._session.scalar(
            select(DetectionRun).order_by(
                DetectionRun.started_at.desc(), DetectionRun.run_id.desc()
            ).limit(1)
        )
        schema_revision = self._session.scalar(
            text("SELECT version_num FROM alembic_version")
        )

        return {
            "records": record_metrics,
            "active_rules": int(
                self._session.scalar(
                    select(func.count())
                    .select_from(MonitoringRule)
                    .where(MonitoringRule.is_active)
                )
                or 0
            ),
            "last_run": last_run,
            "active_users": int(
                self._session.scalar(
                    select(func.count())
                    .select_from(AppUser)
                    .join(AppRole)
                    .where(AppUser.is_active, AppRole.is_active)
                )
                or 0
            ),
            "total_users": int(
                self._session.scalar(select(func.count()).select_from(AppUser))
                or 0
            ),
            "audit_counts": {
                "failed_logins_last_24h": int(audit_counts.get("LOGIN_FAILED", 0)),
                "access_denied_last_24h": int(audit_counts.get("ACCESS_DENIED", 0)),
            },
            "schema_revision": schema_revision,
        }

    def funnel_data(self, since: datetime) -> dict[str, Any]:
        """Where did the alerts created since `since` go? (K3 'Alarm akışı').

        An alert counts as escalated when it was ever in in_review (or is confirmed,
        which legacy data could reach directly). Outcome = current status.
        created = analyst_closed + analyst_open + escalated always holds.
        decision_days: created -> latest closing decision (closed or confirmed)
        in alert_status_history; alerts decided without history are left out.
        """
        row = self._session.execute(
            text(
                """
                WITH created AS (
                    SELECT a.alert_id, a.status,
                           (a.status IN ('in_review', 'confirmed_suspicious')
                            OR EXISTS (SELECT 1 FROM alert_status_history h
                                       WHERE h.alert_id = a.alert_id
                                         AND h.new_status = 'in_review')) AS escalated,
                           CASE WHEN a.status IN ('closed', 'confirmed_suspicious') THEN
                               (SELECT EXTRACT(EPOCH FROM (MAX(h.changed_at) - a.created_at)) / 86400.0
                                FROM alert_status_history h
                                WHERE h.alert_id = a.alert_id
                                  AND h.new_status IN ('closed', 'confirmed_suspicious'))
                           END AS decision_days
                    FROM alert a WHERE a.created_at >= :since
                )
                SELECT COUNT(*) AS created,
                       COUNT(*) FILTER (WHERE NOT escalated AND status = 'closed') AS analyst_closed,
                       COUNT(*) FILTER (WHERE NOT escalated AND status <> 'closed') AS analyst_open,
                       COUNT(*) FILTER (WHERE escalated) AS escalated,
                       COUNT(*) FILTER (WHERE escalated AND status = 'confirmed_suspicious') AS confirmed,
                       COUNT(*) FILTER (WHERE escalated AND status = 'closed') AS escalated_closed,
                       COUNT(*) FILTER (WHERE escalated AND status = 'new') AS returned,
                       COUNT(*) FILTER (WHERE escalated AND status = 'in_review') AS pending,
                       COUNT(*) FILTER (WHERE status IN ('new', 'in_review')) AS open,
                       AVG(decision_days) AS avg_decision_days
                FROM created
                """
            ),
            {"since": since},
        ).mappings().one()
        return dict(row)

    def rule_performance_data(self, since: datetime) -> list[dict[str, Any]]:
        rows = self._session.execute(
            text(
                """
                SELECT r.rule_code, r.name, r.is_active, r.thresholds,
                       (SELECT COUNT(*) FROM rule_result rr
                        JOIN detection_run dr ON dr.run_id = rr.run_id
                        WHERE rr.rule_id = r.rule_id AND rr.result_status = 'evaluated'
                          AND dr.as_of >= :since) AS evaluated,
                       COUNT(a.alert_id) AS alerts,
                       ROUND(AVG(a.score), 4) AS avg_alert_score,
                       COUNT(a.alert_id) FILTER (WHERE a.status = 'confirmed_suspicious') AS confirmed,
                       COUNT(a.alert_id) FILTER (WHERE a.status = 'closed') AS closed
                FROM monitoring_rule r
                LEFT JOIN alert a ON a.rule_id = r.rule_id AND a.created_at >= :since
                GROUP BY r.rule_id
                ORDER BY r.rule_code
                """
            ),
            {"since": since},
        ).mappings().all()
        return [dict(row) for row in rows]
