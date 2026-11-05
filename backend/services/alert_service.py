from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from backend.services import alert_workflow as workflow
from backend.services.auth_service import AuthenticatedUser
from backend.services.masking import (
    mask_account,
    masked_transaction,
    transaction_direction,
)
from backend.repositories.alert_repository import (
    SqlAlchemyAlertRepository,
    alert_summary,
)
from backend.services.transaction_service import TransactionService


SEVERITY_BY_RANK = {1: "low", 2: "medium", 3: "high"}


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


CONTEXT_MONTHS = 6
CONTEXT_TRANSACTION_LIMIT = 500
CUSTOMER_CONTEXT_CLOSED = "Customer information is only available for open alerts."


def months_before(moment: datetime, months: int) -> datetime:
    """Same day-of-month ``months`` earlier (clamped to the month's last day)."""
    month_index = moment.year * 12 + moment.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    for day in range(moment.day, 0, -1):
        try:
            return moment.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    raise ValueError("Invalid date")


class CustomerContextForbidden(PermissionError):
    pass


class AlertNotFound(LookupError):
    pass


class InvalidAlertUpdate(ValueError):
    pass


class AlertService:
    def __init__(self, repository: SqlAlchemyAlertRepository) -> None:
        self._repository = repository

    def list_alerts(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        rule_code: str | None = None,
        customer_no: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        offset: int = 0,
        limit: int = 50,
        include_counts: bool = False,
    ) -> dict[str, Any]:
        if date_from and date_to and date_from > date_to:
            raise InvalidAlertUpdate("date_from must not be after date_to.")
        total, alerts = self._repository.list_alerts(
            status=status,
            severity=severity,
            rule_code=rule_code,
            customer_no=customer_no,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=limit,
        )
        page: dict[str, Any] = {"total": total, "items": [alert_summary(alert) for alert in alerts]}
        if include_counts:
            counts = self._repository.count_alerts_by_status(
                severity=severity,
                rule_code=rule_code,
                customer_no=customer_no,
                date_from=date_from,
                date_to=date_to,
            )
            page["counts_by_status"] = {
                status: counts.get(status, 0)
                for status in ("new", "in_review", "closed", "confirmed_suspicious")
            }
        return page

    def alert_queue(
        self,
        *,
        status: str = "new",
        severity: str | None = None,
        rule_code: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        q: str | None = None,
        sort: str = "severity_age",
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        if date_from and date_to and date_from > date_to:
            raise InvalidAlertUpdate("date_from must not be after date_to.")
        summary, total, rows = self._repository.alert_queue(
            status=status,
            severity=severity,
            rule_code=rule_code,
            date_from=date_from,
            date_to=date_to,
            q=(q or "").strip() or None,
            sort=sort,
            offset=offset,
            limit=limit,
        )
        items = []
        for row in rows:
            last_event = None
            if row["last_new_status"] is not None:
                last_event = {
                    "old_status": row["last_old_status"],
                    "new_status": row["last_new_status"],
                    "changed_at": row["last_changed_at"],
                    "actor_name": row["last_actor_name"],
                }
            returned = (
                row["last_old_status"] == "in_review" and row["last_new_status"] == "new"
            )
            escalated = (
                row["last_old_status"] == "new" and row["last_new_status"] == "in_review"
            )
            items.append(
                {
                    "customer_no": row["customer_no"],
                    "customer_name": row["customer_name"],
                    "customer_type": row["customer_type"],
                    "rule_codes": sorted(row["rule_codes"]),
                    "severity": SEVERITY_BY_RANK[row["severity_rank"]],
                    "max_score": row["max_score"],
                    "alert_count": row["alert_count"],
                    "transaction_count": row["transaction_count"],
                    "oldest_created_at": row["oldest_created_at"],
                    "escalated_at": row["escalated_at"],
                    "alert_ids": list(row["alert_ids"]),
                    "last_event": last_event,
                    "returned_by": row["last_actor_name"] if returned else None,
                    "returned_note": row["last_note"] if returned else None,
                    "escalated_by": row["last_actor_name"] if escalated else None,
                    "escalation_note": row["last_note"] if escalated else None,
                }
            )
        return {"summary": summary, "total": total, "items": items}

    def my_summary(self, user_id: int) -> dict[str, Any]:
        now = datetime.now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        data = self._repository.my_summary(user_id, day_start)
        cases: dict[str, dict[str, Any]] = {}
        for row in data["returned"]:
            case = cases.setdefault(
                row["customer_no"],
                {
                    "customer_no": row["customer_no"],
                    "customer_name": row["customer_name"],
                    "rule_codes": [],
                    "alert_ids": [],
                    "returned_by": row["returned_by"],
                    "returned_at": row["returned_at"],
                    "note": row["note"],
                },
            )
            if row["rule_code"] not in case["rule_codes"]:
                case["rule_codes"].append(row["rule_code"])
            case["alert_ids"].append(row["alert_id"])
        return {
            "decided_today": int(data["counts"]["decided_today"] or 0),
            "escalated_today": int(data["counts"]["escalated_today"] or 0),
            "returned_to_me": len(data["returned"]),
            "returned_cases": list(cases.values()),
        }

    def list_rule_codes(self) -> list[str]:
        return self._repository.list_rule_codes()

    def get_alert(
        self, alert_id: int, permissions: frozenset[str] | set[str] = frozenset()
    ) -> dict[str, Any]:
        alert = self._repository.get_alert(alert_id)
        if alert is None:
            raise AlertNotFound("Alert not found.")
        result = alert_summary(alert)
        full_view = "customer:view" in permissions
        transactions = [relation.transaction for relation in alert.transactions]
        transactions.sort(key=lambda tx: (tx.tx_time, tx.transaction_id))
        result["transactions"] = [
            {
                **TransactionService.transaction_view(tx),
                "view": "full",
                "direction": transaction_direction(tx, alert.customer_id),
                "in_alert": True,
            }
            if full_view
            else masked_transaction(tx, alert.customer_id, in_alert=True)
            for tx in transactions
        ]
        result["explanation"] = self._explanation(alert)
        result["events"] = [
            {"action": event.action, "created_at": event.created_at, "details": event.details}
            for event in self._repository.alert_events(alert_id)
        ]
        history = []
        escalated_by = None
        for event, actor_name, actor_role in self._repository.history_with_actors(alert_id):
            history.append(
                {
                    "old_status": event.old_status,
                    "new_status": event.new_status,
                    "note": event.note,
                    "changed_at": event.changed_at,
                    "changed_by": event.changed_by,
                    "actor_name": actor_name,
                    "actor_role": actor_role,
                }
            )
            if event.new_status == "in_review":
                escalated_by = {
                    "user_id": event.changed_by,
                    "actor_name": actor_name,
                    "changed_at": event.changed_at,
                }
        result["history"] = history
        result["escalated_by"] = escalated_by
        return result

    def _explanation(self, alert: Any) -> dict[str, Any] | None:
        source = self._repository.explanation_source(alert)
        if source is None:
            return None  # legacy rules (R1-R4) or no stored run: ALR031
        rule_result, run = source
        snapshot = rule_result.parameter_snapshot or {}
        values = snapshot.get("values", {}) if isinstance(snapshot, dict) else {}
        return {
            "rule_code": alert.rule.rule_code,
            "rule_name": alert.rule.name,
            "alert_mode": rule_result.alert_mode,
            "customer_type": rule_result.customer_type,
            "parameter_status": rule_result.parameter_status,
            "raw_x": rule_result.raw_x,
            "score": rule_result.score,
            "x_esik": _optional_str(values.get("x_esik")),
            "x_kesin": _optional_str(values.get("x_kesin")),
            "parameters": values,
            "steps": rule_result.step_trace or [],
            "run": {"run_id": str(run.run_id), "as_of": run.as_of},
        }

    def decide(
        self,
        alert_ids: list[int],
        target: str,
        note: str | None,
        user: AuthenticatedUser,
        *,
        single: bool = False,
    ) -> dict[str, Any]:
        """Apply one decision to one or more alerts atomically.

        Check order follows API design 7.1 (single PATCH) and 7.3 (bulk). Nothing
        is written unless every alert passes every check.
        """
        if single:
            workflow.ensure_target_permission(user.permissions, target)
        else:
            normalized_note = workflow.normalize_note(note)
        alerts = self._repository.lock_alerts(alert_ids)
        try:
            found = {alert.alert_id for alert in alerts}
            for alert_id in alert_ids:
                if alert_id not in found:
                    raise workflow.WorkflowError(
                        404, workflow.MSG_ALERT_NOT_FOUND, alert_id=alert_id
                    )
            if not single:
                workflow.ensure_target_permission(user.permissions, target)
                first = alerts[0]
                for alert in alerts[1:]:
                    if alert.customer_id != first.customer_id:
                        raise workflow.WorkflowError(
                            422, workflow.MSG_DIFFERENT_CUSTOMERS, alert_id=alert.alert_id
                        )
                for alert in alerts[1:]:
                    if alert.status != first.status:
                        raise workflow.WorkflowError(
                            422, workflow.MSG_DIFFERENT_STATUSES, alert_id=alert.alert_id
                        )
            escalators = self._repository.last_escalators(alert_ids)
            for alert in alerts:
                workflow.check_transition(
                    permissions=user.permissions,
                    user_id=user.user_id,
                    alert_id=alert.alert_id,
                    current=alert.status,
                    target=target,
                    escalated_by=escalators.get(alert.alert_id),
                )
            if single:
                normalized_note = workflow.normalize_note(note)
        except workflow.WorkflowError:
            self._repository.release()
            raise
        decision_id = str(uuid4())
        decided_at = self._repository.apply_decision(
            alerts, target, normalized_note, user.user_id, decision_id
        )
        return {
            "decision_id": decision_id,
            "status": target,
            "alert_ids": [alert.alert_id for alert in alerts],
            "decided_at": decided_at,
        }

    def update_status(
        self, alert_id: int, status: str, note: str | None, user: AuthenticatedUser
    ) -> dict[str, Any]:
        self.decide([alert_id], status, note, user, single=True)
        return {"alert_id": alert_id, "status": status, "changed": True}

    def customer_context(self, alert_id: int, user: AuthenticatedUser) -> dict[str, Any]:
        """Customer profile, per-currency summary and masked last-6-month activity (K4).

        Analysts only for alerts in 'new'; alert:confirm (compliance) for any status.
        The view is logged (K6) before the data is returned.
        """
        alert = self._repository.get_alert_for_context(alert_id)
        if alert is None:
            raise AlertNotFound("Alert not found.")
        if alert.status != "new" and "alert:confirm" not in user.permissions:
            raise CustomerContextForbidden(CUSTOMER_CONTEXT_CLOSED)
        customer = alert.customer
        now = datetime.now()
        since_6m = months_before(now, CONTEXT_MONTHS)
        since_30d = now - timedelta(days=30)
        accounts = [account for account in customer.accounts if account.is_active]
        account_ids = [account.account_id for account in accounts]
        alert_tx_ids = {relation.transaction_id for relation in alert.transactions}
        rows = self._repository.context_transactions(
            account_ids, since_6m, CONTEXT_TRANSACTION_LIMIT + 1
        )
        summary = [
            {
                "currency": row["currency"],
                "incoming_30d": row["incoming_30d"],
                "outgoing_30d": row["outgoing_30d"],
                "avg_monthly_outgoing_6m": (
                    Decimal(row["outgoing_6m"]) / CONTEXT_MONTHS
                ).quantize(Decimal("0.01")),
            }
            for row in self._repository.context_summary(account_ids, since_30d, since_6m)
        ]
        result = {
            "alert_id": alert.alert_id,
            "period_start": since_6m,
            "profile": {
                "customer_type": customer.customer_type,
                "occupation": customer.occupation,
                "monthly_income": customer.monthly_income,
                "risk_level": customer.risk_level,
                "customer_since": customer.created_at.year if customer.created_at else None,
            },
            "accounts": [
                {
                    "account": mask_account(account.account_no),
                    "currency": account.currency,
                    "type": account.account_type,
                }
                for account in accounts
            ],
            "summary": summary,
            "transactions": [
                masked_transaction(
                    tx, customer.customer_id, in_alert=tx.transaction_id in alert_tx_ids
                )
                for tx in rows[:CONTEXT_TRANSACTION_LIMIT]
            ],
            "truncated": len(rows) > CONTEXT_TRANSACTION_LIMIT,
        }
        self._repository.log_customer_views(
            user.user_id, [customer.customer_no], "alert_detail"
        )
        return result
