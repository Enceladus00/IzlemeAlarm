from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased, joinedload, selectinload

from backend.detection.evidence import (
    alert_severity,
    daily_deduplication_key,
    max_severity,
    raise_severity,
)
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


ALERT_THRESHOLD = Decimal("0.5")
OPEN_STATUSES = ("new", "in_review")
# Arbitrary application-wide key for pg_advisory_xact_lock (alert persistence).
ALERT_PERSIST_LOCK_KEY = 7_311_009


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

    def _persist_alerts(
        self,
        results: list[RuleResultEvidence],
        rules_by_code: dict[str, MonitoringRule],
        as_of: datetime,
        run_id: UUID,
    ) -> list[int]:
        """Open, rescore or extend alerts for qualifying results (K9).

        * An open (new / in_review) alert for the same rule and customer is reused:
          a higher score updates score and severity (severity never decreases, so an
          R17 escalation survives), and new evidence transactions are attached.
        * Otherwise a new alert is created. If today's daily key already belongs to
          an alert that was closed, a numbered key is used so the re-trigger is not
          silently merged into the closed alert.
        Returns the ids of newly created alerts.
        """
        if not results:
            return []
        pairs = {
            (rules_by_code[result.rule_code].rule_id, result.customer_id)
            for result in results
        }
        open_alerts: dict[tuple[int, int], Alert] = {}
        for alert in self._session.scalars(
            select(Alert)
            .where(
                tuple_(Alert.rule_id, Alert.customer_id).in_(list(pairs)),
                Alert.status.in_(OPEN_STATUSES),
            )
            .order_by(Alert.created_at, Alert.alert_id)
        ):
            open_alerts[(alert.rule_id, alert.customer_id)] = alert  # newest wins
        created_ids: list[int] = []
        links: list[dict[str, int]] = []
        for result in results:
            rule_id = rules_by_code[result.rule_code].rule_id
            score = result.score
            assert score is not None
            transaction_ids = list(
                dict.fromkeys(tx.transaction_id for tx in result.transactions)
            )
            alert = open_alerts.get((rule_id, result.customer_id))
            if alert is not None:
                if alert.score is None or score > alert.score:
                    old_score = alert.score
                    old_severity = alert.severity
                    alert.score = score
                    alert.severity = max_severity(alert.severity, alert_severity(score))
                    self._session.add(
                        AuditLog(
                            actor_id=None,
                            action="alert.rescored",
                            entity_type="alert",
                            entity_id=str(alert.alert_id),
                            details={
                                "old_score": None if old_score is None else str(old_score),
                                "new_score": str(score),
                                "old_severity": old_severity,
                                "new_severity": alert.severity,
                                "run_id": str(run_id),
                            },
                        )
                    )
            else:
                base_key = daily_deduplication_key(
                    result.rule_code, result.customer_id, as_of.date()
                )
                taken = set(
                    self._session.scalars(
                        select(Alert.deduplication_key).where(
                            (Alert.deduplication_key == base_key)
                            | Alert.deduplication_key.like(f"{base_key}:%")
                        )
                    )
                )
                key = base_key
                sequence = 1
                while key in taken:
                    sequence += 1
                    key = f"{base_key}:{sequence}"
                alert = Alert(
                    rule_id=rule_id,
                    customer_id=result.customer_id,
                    severity=alert_severity(score),
                    score=score,
                    status="new",
                    deduplication_key=key,
                )
                self._session.add(alert)
                self._session.flush()
                open_alerts[(rule_id, result.customer_id)] = alert
                created_ids.append(alert.alert_id)
            links.extend(
                {"alert_id": alert.alert_id, "transaction_id": transaction_id}
                for transaction_id in transaction_ids
            )
        if links:
            self._session.execute(
                insert(AlertTransaction).values(links).on_conflict_do_nothing()
            )
        return created_ids

    def _apply_r17(
        self,
        pairs: list[tuple[RuleResultEvidence, RuleResult]],
        rules_by_code: dict[str, MonitoringRule],
        as_of: datetime,
        run_id: UUID,
    ) -> None:
        """R17: raise the severity of a customer's open alerts one step when they
        come from at least `min_rules` different rules (API design 7.12).

        Runs inside persist_run's transaction, after this run's alerts are saved.
        Each alert is raised by R17 at most once.
        """
        if not pairs:
            return
        self._session.flush()
        code_by_id = {rule.rule_id: code for code, rule in rules_by_code.items()}
        for result, row in pairs:
            values = result.parameter_snapshot["values"]
            statuses = list(values["open_statuses"])
            excluded = set(values["excluded_rules"])
            since = as_of - timedelta(days=int(values["window_days"]))
            alerts = list(
                self._session.scalars(
                    select(Alert)
                    .where(
                        Alert.customer_id == result.customer_id,
                        Alert.status.in_(statuses),
                    )
                    .order_by(Alert.alert_id)
                )
            )
            counted = {
                alert.rule_id
                for alert in alerts
                if alert.created_at >= since and code_by_id.get(alert.rule_id) not in excluded
            }
            k = len(counted)
            raised: list[dict[str, object]] = []
            if k >= int(values["min_rules"]):
                already = set(
                    self._session.scalars(
                        select(AuditLog.entity_id).where(
                            AuditLog.action == "alert.severity_raised",
                            AuditLog.entity_type == "alert",
                            AuditLog.entity_id.in_([str(alert.alert_id) for alert in alerts]),
                        )
                    )
                )
                for alert in alerts:
                    if str(alert.alert_id) in already:
                        continue
                    old = alert.severity
                    new = raise_severity(old)
                    if new == old:
                        continue
                    alert.severity = new
                    raised.append({"alert_id": alert.alert_id, "old": old, "new": new})
                    self._session.add(
                        AuditLog(
                            actor_id=None,
                            action="alert.severity_raised",
                            entity_type="alert",
                            entity_id=str(alert.alert_id),
                            details={
                                "rule": "R17",
                                "K": k,
                                "old": old,
                                "new": new,
                                "run_id": str(run_id),
                            },
                        )
                    )
            row.step_trace = [
                {**row.step_trace[0], "status": "completed", "details": {
                    "K": k,
                    "counted_rules": sorted(code_by_id.get(rule_id, "?") for rule_id in counted),
                    "window_days": values["window_days"],
                    "excluded_rules": sorted(excluded),
                }},
                {**row.step_trace[1], "status": "completed" if k >= int(values["min_rules"]) else "skipped", "details": {
                    "min_rules": values["min_rules"],
                    "raised": raised,
                }},
                {**row.step_trace[2], "status": "completed", "details": {
                    "raised_count": len(raised),
                }},
            ]

    def persist_run(
        self,
        run_id: UUID,
        as_of: datetime,
        evaluation: DetectionEvaluation,
        rules_by_code: dict[str, MonitoringRule],
        *,
        actor_id: int | None = None,
        automatic: bool = False,
        started_at: datetime | None = None,
    ) -> int:
        run_started_at = started_at or datetime.now()
        run = DetectionRun(
            run_id=run_id,
            as_of=as_of,
            status="completed",
            started_at=run_started_at,
            summary=evaluation.summary,
        )
        # K9: serialise alert persistence across concurrent runs (upload auto-run
        # vs. manual run) so two runs cannot both open an alert for the same
        # rule and customer. Released automatically at commit/rollback.
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ALERT_PERSIST_LOCK_KEY}
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

        created_alerts = self._persist_alerts(
            [
                result
                for result, _row in result_pairs
                if result.alert_mode == "ALERT"
                and result.result_status == "evaluated"
                and result.score is not None
                and result.score >= (result.alert_threshold or ALERT_THRESHOLD)
            ],
            rules_by_code,
            as_of,
            run_id,
        )
        self._apply_r17(
            [
                (result, row)
                for result, row in result_pairs
                if result.rule_code == "R17" and result.result_status == "evaluated"
            ],
            rules_by_code,
            as_of,
            run_id,
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
        completed_at = datetime.now()
        run.completed_at = completed_at
        run.duration_ms = max(
            0, int((completed_at - run_started_at).total_seconds() * 1000)
        )
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return created
