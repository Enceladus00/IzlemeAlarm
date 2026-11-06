from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.repositories.customer_view_log import log_customer_views
from backend.models import (
    Account,
    Alert,
    AlertStatusHistory,
    AppRole,
    AppUser,
    AlertTransaction,
    AuditLog,
    Customer,
    DetectionRun,
    MonitoringRule,
    RuleResult,
    Transaction,
)


class SqlAlchemyAlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_alerts(
        self,
        *,
        status: str | None,
        severity: str | None,
        rule_code: str | None,
        customer_no: str | None,
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
        filters = []
        if severity:
            filters.append(Alert.severity == severity)
        if rule_code:
            filters.append(MonitoringRule.rule_code == rule_code)
        if customer_no:
            filters.append(Customer.customer_no == customer_no)
        if date_from:
            filters.append(Alert.created_at >= datetime.combine(date_from, time.min))
        if date_to:
            filters.append(
                Alert.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
            )
        query = query.where(*filters)
        if status:
            query = query.where(Alert.status == status)
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

    def count_alerts_by_status(
        self,
        *,
        severity: str | None,
        rule_code: str | None,
        customer_no: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, int]:
        """E11: alert counts per status under the same filters (status excluded)."""
        query = (
            select(Alert.status, func.count())
            .join(Alert.customer)
            .join(Alert.rule)
            .group_by(Alert.status)
        )
        if severity:
            query = query.where(Alert.severity == severity)
        if rule_code:
            query = query.where(MonitoringRule.rule_code == rule_code)
        if customer_no:
            query = query.where(Customer.customer_no == customer_no)
        if date_from:
            query = query.where(Alert.created_at >= datetime.combine(date_from, time.min))
        if date_to:
            query = query.where(
                Alert.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
            )
        return {status: int(count) for status, count in self._session.execute(query)}

    def alert_queue(
        self,
        *,
        status: str,
        severity: str | None,
        rule_code: str | None,
        date_from: date | None,
        date_to: date | None,
        q: str | None,
        sort: str,
        offset: int,
        limit: int,
    ) -> tuple[dict[str, int], int, list[dict[str, Any]]]:
        """Customer-grouped alert queue (K1). Returns (summary, total, rows).

        Filters apply per alert; a customer appears when at least one of its alerts
        matches. Summary counts cover every matching alert, not just the page.
        """
        conditions = ["a.status = :status"]
        params: dict[str, Any] = {"status": status}
        if severity:
            conditions.append("a.severity = :severity")
            params["severity"] = severity
        if rule_code:
            conditions.append("r.rule_code = :rule_code")
            params["rule_code"] = rule_code
        if date_from:
            conditions.append("a.created_at >= :date_from")
            params["date_from"] = datetime.combine(date_from, time.min)
        if date_to:
            conditions.append("a.created_at < :date_to")
            params["date_to"] = datetime.combine(date_to + timedelta(days=1), time.min)
        if q:
            escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
            conditions.append("(c.full_name ILIKE :q OR c.customer_no ILIKE :q)")
            params["q"] = f"%{escaped}%"
        cte = f"""
            WITH filtered AS (
                SELECT a.alert_id, a.customer_id, a.severity, a.score, a.created_at,
                       r.rule_code,
                       CASE a.severity WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END
                           AS severity_rank
                FROM alert a
                JOIN customer c ON c.customer_id = a.customer_id
                JOIN monitoring_rule r ON r.rule_id = a.rule_id
                WHERE {' AND '.join(conditions)}
            ),
            groups AS (
                SELECT customer_id,
                       COUNT(*) AS alert_count,
                       MAX(severity_rank) AS severity_rank,
                       MAX(score) AS max_score,
                       MIN(created_at) AS oldest_created_at,
                       ARRAY_AGG(alert_id ORDER BY created_at, alert_id) AS alert_ids,
                       ARRAY_AGG(DISTINCT rule_code) AS rule_codes,
                       COUNT(*) FILTER (WHERE severity = 'high') AS high_alerts
                FROM filtered GROUP BY customer_id
            ),
            last_events AS (
                SELECT DISTINCT ON (f.customer_id)
                       f.customer_id, h.old_status, h.new_status, h.changed_at, h.note,
                       u.username AS actor_name
                FROM filtered f
                JOIN alert_status_history h ON h.alert_id = f.alert_id
                LEFT JOIN app_user u ON u.user_id = h.changed_by
                ORDER BY f.customer_id, h.changed_at DESC, h.history_id DESC
            ),
            escalations AS (
                SELECT f.customer_id, MIN(e.escalated_at) AS escalated_at
                FROM filtered f
                JOIN LATERAL (
                    SELECT MAX(h.changed_at) AS escalated_at
                    FROM alert_status_history h
                    WHERE h.alert_id = f.alert_id AND h.new_status = 'in_review'
                ) e ON e.escalated_at IS NOT NULL
                GROUP BY f.customer_id
            )
        """
        summary_row = self._session.execute(
            text(
                cte
                + """
                SELECT COALESCE(SUM(g.alert_count), 0) AS alerts,
                       COUNT(*) AS customers,
                       COALESCE(SUM(g.high_alerts), 0) AS high_alerts,
                       COUNT(*) FILTER (WHERE g.high_alerts > 0) AS high_customers,
                       COUNT(*) FILTER (
                           WHERE le.old_status = 'in_review' AND le.new_status = 'new'
                       ) AS returned_customers
                FROM groups g LEFT JOIN last_events le ON le.customer_id = g.customer_id
                """
            ),
            params,
        ).mappings().one()
        summary = {key: int(value) for key, value in summary_row.items()}
        order = (
            "es.escalated_at ASC NULLS LAST, c.customer_no ASC"
            if sort == "waiting"
            else "g.severity_rank DESC, g.oldest_created_at ASC, c.customer_no ASC"
        )
        rows = self._session.execute(
            text(
                cte
                + f"""
                SELECT g.customer_id, c.customer_no, c.full_name AS customer_name,
                       c.customer_type, g.alert_count, g.severity_rank, g.max_score,
                       g.oldest_created_at, g.alert_ids, g.rule_codes,
                       es.escalated_at,
                       le.old_status AS last_old_status, le.new_status AS last_new_status,
                       le.changed_at AS last_changed_at, le.note AS last_note,
                       le.actor_name AS last_actor_name,
                       (SELECT COUNT(DISTINCT at.transaction_id) FROM alert_transaction at
                        WHERE at.alert_id = ANY(g.alert_ids)) AS transaction_count
                FROM groups g
                JOIN customer c ON c.customer_id = g.customer_id
                LEFT JOIN last_events le ON le.customer_id = g.customer_id
                LEFT JOIN escalations es ON es.customer_id = g.customer_id
                ORDER BY {order}
                OFFSET :offset LIMIT :limit
                """
            ),
            {**params, "offset": offset, "limit": limit},
        ).mappings().all()
        return summary, summary["customers"], [dict(row) for row in rows]

    def my_summary(self, user_id: int, day_start: datetime) -> dict[str, Any]:
        """Counts for the signed-in user only (no other user's data)."""
        counts = self._session.execute(
            text(
                """
                SELECT
                  COUNT(DISTINCT alert_id) FILTER (
                      WHERE old_status IS DISTINCT FROM new_status
                  ) AS decided_today,
                  COUNT(*) FILTER (
                      WHERE old_status = 'new' AND new_status = 'in_review'
                  ) AS escalated_today
                FROM alert_status_history
                WHERE changed_by = :user_id AND changed_at >= :day_start
                """
            ),
            {"user_id": user_id, "day_start": day_start},
        ).mappings().one()
        # Alerts currently 'new' whose latest event is a return (in_review -> new)
        # and whose latest escalation before that was made by this user.
        returned = self._session.execute(
            text(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (h.alert_id)
                           h.alert_id, h.old_status, h.new_status, h.changed_at,
                           h.note, h.changed_by
                    FROM alert_status_history h
                    ORDER BY h.alert_id, h.changed_at DESC, h.history_id DESC
                ),
                escalation AS (
                    SELECT DISTINCT ON (h.alert_id) h.alert_id, h.changed_by
                    FROM alert_status_history h
                    WHERE h.new_status = 'in_review'
                    ORDER BY h.alert_id, h.changed_at DESC, h.history_id DESC
                )
                SELECT a.alert_id, c.customer_no, c.full_name AS customer_name,
                       r.rule_code, l.changed_at AS returned_at, l.note,
                       u.username AS returned_by
                FROM alert a
                JOIN latest l ON l.alert_id = a.alert_id
                JOIN escalation e ON e.alert_id = a.alert_id
                JOIN customer c ON c.customer_id = a.customer_id
                JOIN monitoring_rule r ON r.rule_id = a.rule_id
                LEFT JOIN app_user u ON u.user_id = l.changed_by
                WHERE a.status = 'new' AND l.old_status = 'in_review'
                  AND l.new_status = 'new' AND e.changed_by = :user_id
                ORDER BY l.changed_at DESC, a.alert_id
                """
            ),
            {"user_id": user_id},
        ).mappings().all()
        # E08: the shared analyst queue, and what became of this user's escalations.
        queue = self._session.execute(
            text(
                """
                SELECT COUNT(*) AS queue_pending,
                       COUNT(*) FILTER (WHERE severity = 'high') AS queue_high
                FROM alert WHERE status = 'new'
                """
            )
        ).mappings().one()
        escalations = self._session.execute(
            text(
                """
                WITH mine AS (
                    SELECT h.alert_id, MIN(h.changed_at) AS first_escalated_at
                    FROM alert_status_history h
                    WHERE h.changed_by = :user_id AND h.new_status = 'in_review'
                      AND h.changed_at >= :since
                    GROUP BY h.alert_id
                )
                SELECT COUNT(*) AS escalations_30d,
                       COUNT(*) FILTER (WHERE a.status = 'confirmed_suspicious') AS confirmed,
                       COUNT(*) FILTER (WHERE a.status = 'closed') AS closed,
                       COUNT(*) FILTER (WHERE a.status = 'new') AS returned,
                       COUNT(*) FILTER (WHERE a.status = 'in_review') AS pending,
                       COUNT(*) FILTER (WHERE m.first_escalated_at >= :day_start
                                          AND a.status = 'confirmed_suspicious')
                           AS escalated_today_confirmed
                FROM mine m JOIN alert a ON a.alert_id = m.alert_id
                """
            ),
            {"user_id": user_id, "since": day_start - timedelta(days=29), "day_start": day_start},
        ).mappings().one()
        decisions = self._session.execute(
            text(
                """
                SELECT h.alert_id, h.old_status, h.new_status, h.changed_at, h.note,
                       c.customer_no, c.full_name AS customer_name, r.rule_code, a.severity
                FROM alert_status_history h
                JOIN alert a ON a.alert_id = h.alert_id
                JOIN customer c ON c.customer_id = a.customer_id
                JOIN monitoring_rule r ON r.rule_id = a.rule_id
                WHERE h.changed_by = :user_id AND h.changed_at >= :day_start
                  AND h.old_status IS DISTINCT FROM h.new_status
                ORDER BY h.changed_at DESC, h.history_id DESC
                LIMIT 100
                """
            ),
            {"user_id": user_id, "day_start": day_start},
        ).mappings().all()
        closed_today = self._session.execute(
            text(
                """
                SELECT COUNT(DISTINCT alert_id) FROM alert_status_history
                WHERE changed_by = :user_id AND changed_at >= :day_start
                  AND new_status = 'closed'
                """
            ),
            {"user_id": user_id, "day_start": day_start},
        ).scalar_one()
        return {
            "counts": {**dict(counts), **dict(queue), "closed_today": closed_today},
            "escalations": dict(escalations),
            "decisions": [dict(row) for row in decisions],
            "returned": [dict(row) for row in returned],
        }

    def list_rule_codes(self) -> list[str]:
        return list(
            self._session.scalars(
                select(MonitoringRule.rule_code).order_by(MonitoringRule.rule_code)
            )
        )

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

    def lock_alerts(self, alert_ids: list[int]) -> list[Alert]:
        """Load and row-lock alerts (FOR UPDATE) in a stable order to avoid deadlocks."""
        return list(
            self._session.scalars(
                select(Alert)
                .where(Alert.alert_id.in_(alert_ids))
                .order_by(Alert.alert_id)
                .with_for_update(of=Alert)
            )
        )

    def last_escalators(self, alert_ids: list[int]) -> dict[int, int]:
        """alert_id -> user who most recently moved the alert to in_review."""
        if not alert_ids:
            return {}
        rows = self._session.execute(
            select(AlertStatusHistory.alert_id, AlertStatusHistory.changed_by)
            .where(
                AlertStatusHistory.alert_id.in_(alert_ids),
                AlertStatusHistory.new_status == "in_review",
            )
            .order_by(AlertStatusHistory.changed_at, AlertStatusHistory.history_id)
        ).all()
        # Later rows overwrite earlier ones: the most recent escalation wins.
        return {alert_id: changed_by for alert_id, changed_by in rows}

    def apply_decision(
        self,
        alerts: list[Alert],
        new_status: str,
        note: str,
        actor_id: int,
        decision_id: str,
    ) -> datetime:
        """Write the decision for every alert in ONE transaction (K2)."""
        decided_at = datetime.now()
        try:
            for alert in alerts:
                old_status = alert.status
                self._session.add(
                    AlertStatusHistory(
                        alert_id=alert.alert_id,
                        changed_by=actor_id,
                        old_status=old_status,
                        new_status=new_status,
                        note=note,
                        changed_at=decided_at,
                    )
                )
                self._session.add(
                    AuditLog(
                        actor_id=actor_id,
                        action="alert.status_changed",
                        entity_type="alert",
                        entity_id=str(alert.alert_id),
                        details={
                            "old_status": old_status,
                            "new_status": new_status,
                            "note": note,
                            "decision_id": decision_id,
                        },
                    )
                )
                alert.status = new_status
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return decided_at

    def release(self) -> None:
        """End the transaction (and its row locks) without writing anything."""
        self._session.rollback()

    def get_alert_for_context(self, alert_id: int) -> Alert | None:
        return self._session.scalar(
            select(Alert)
            .where(Alert.alert_id == alert_id)
            .options(
                joinedload(Alert.customer).selectinload(Customer.accounts),
                selectinload(Alert.transactions),
            )
        )

    def context_transactions(
        self, account_ids: list[int], since: datetime, limit: int
    ) -> list[Transaction]:
        if not account_ids:
            return []
        return list(
            self._session.scalars(
                select(Transaction)
                .where(
                    Transaction.is_active,
                    Transaction.tx_time >= since,
                    Transaction.sender_account_id.in_(account_ids)
                    | Transaction.receiver_account_id.in_(account_ids),
                )
                .options(
                    joinedload(Transaction.sender_account).joinedload(Account.customer),
                    joinedload(Transaction.receiver_account).joinedload(Account.customer),
                )
                .order_by(Transaction.tx_time.desc(), Transaction.transaction_id.desc())
                .limit(limit)
            ).unique()
        )

    def context_summary(
        self, account_ids: list[int], since_30d: datetime, since_6m: datetime
    ) -> list[dict[str, Any]]:
        """Per-currency totals (amounts in different currencies are never added)."""
        if not account_ids:
            return []
        rows = self._session.execute(
            text(
                """
                SELECT t.currency,
                       COALESCE(SUM(t.amount) FILTER (
                           WHERE t.receiver_account_id = ANY(:accounts) AND t.tx_time >= :d30
                       ), 0) AS incoming_30d,
                       COALESCE(SUM(t.amount) FILTER (
                           WHERE t.sender_account_id = ANY(:accounts) AND t.tx_time >= :d30
                       ), 0) AS outgoing_30d,
                       COALESCE(SUM(t.amount) FILTER (
                           WHERE t.sender_account_id = ANY(:accounts)
                       ), 0) AS outgoing_6m
                FROM "transaction" t
                WHERE t.is_active AND t.tx_time >= :d6m
                  AND (t.sender_account_id = ANY(:accounts)
                       OR t.receiver_account_id = ANY(:accounts))
                GROUP BY t.currency ORDER BY t.currency
                """
            ),
            {"accounts": account_ids, "d30": since_30d, "d6m": since_6m},
        ).mappings().all()
        return [dict(row) for row in rows]

    def log_customer_views(self, actor_id: int, customer_nos: list[str], source: str) -> None:
        log_customer_views(self._session, actor_id, customer_nos, source)

    def explanation_source(
        self, alert: Alert
    ) -> tuple[RuleResult, DetectionRun] | None:
        """The latest evaluated rule_result that produced the alert's current score (K8)."""
        if alert.score is None:
            return None
        row = self._session.execute(
            select(RuleResult, DetectionRun)
            .join(DetectionRun, DetectionRun.run_id == RuleResult.run_id)
            .where(
                RuleResult.rule_id == alert.rule_id,
                RuleResult.customer_id == alert.customer_id,
                RuleResult.result_status == "evaluated",
                RuleResult.score == alert.score,
            )
            .order_by(DetectionRun.as_of.desc(), RuleResult.result_id.desc())
            .limit(1)
        ).first()
        return None if row is None else (row[0], row[1])

    def alert_events(self, alert_id: int) -> list[AuditLog]:
        """System changes to an alert that are not status changes (K9, R17)."""
        return list(
            self._session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.entity_type == "alert",
                    AuditLog.entity_id == str(alert_id),
                    AuditLog.action.in_(("alert.rescored", "alert.severity_raised")),
                )
                .order_by(AuditLog.created_at, AuditLog.audit_id)
            )
        )

    def history_with_actors(
        self, alert_id: int
    ) -> list[tuple[AlertStatusHistory, str | None, str | None]]:
        rows = self._session.execute(
            select(AlertStatusHistory, AppUser.username, AppRole.role_code)
            .outerjoin(AppUser, AppUser.user_id == AlertStatusHistory.changed_by)
            .outerjoin(AppRole, AppRole.role_id == AppUser.role_id)
            .where(AlertStatusHistory.alert_id == alert_id)
            .order_by(AlertStatusHistory.changed_at, AlertStatusHistory.history_id)
        ).all()
        return [(row[0], row[1], row[2]) for row in rows]


def alert_summary(alert: Alert) -> dict[str, Any]:
    return {
        "alert_id": alert.alert_id,
        "rule_code": alert.rule.rule_code,
        "rule_name": alert.rule.name,
        "customer_no": alert.customer.customer_no,
        "customer_name": alert.customer.full_name,
        "customer": {
            "customer_no": alert.customer.customer_no,
            "customer_name": alert.customer.full_name,
            "customer_type": alert.customer.customer_type,
        },
        "severity": alert.severity,
        "score": alert.score,
        "status": alert.status,
        "created_at": alert.created_at,
        "transaction_count": len(alert.transactions),
        "transaction_ids": [
            relation.transaction_id for relation in alert.transactions
        ],
    }
