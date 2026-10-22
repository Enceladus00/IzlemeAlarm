from datetime import date
from typing import Any

from backend.models import Alert
from backend.repositories.alert_repository import (
    SqlAlchemyAlertRepository,
    alert_summary,
)
from backend.services.transaction_service import TransactionService


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
        date_from: date | None = None,
        date_to: date | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        if date_from and date_to and date_from > date_to:
            raise InvalidAlertUpdate("date_from must not be after date_to.")
        total, alerts = self._repository.list_alerts(
            status=status,
            severity=severity,
            rule_code=rule_code,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=limit,
        )
        return {"total": total, "items": [alert_summary(alert) for alert in alerts]}

    def get_alert(self, alert_id: int) -> dict[str, Any]:
        alert = self._repository.get_alert(alert_id)
        if alert is None:
            raise AlertNotFound("Alert not found.")
        result = alert_summary(alert)
        result["transactions"] = [
            TransactionService.transaction_view(relation.transaction)
            for relation in alert.transactions
        ]
        result["history"] = [
            {
                "old_status": event.old_status,
                "new_status": event.new_status,
                "note": event.note,
                "changed_at": event.changed_at,
            }
            for event in alert.history
        ]
        return result

    def update_status(
        self, alert_id: int, status: str, note: str | None
    ) -> dict[str, Any]:
        alert: Alert | None = self._repository.get_alert_status(alert_id)
        if alert is None:
            raise AlertNotFound("Alert not found.")
        normalized_note = note.strip() if note else None
        if status in {"closed", "confirmed_suspicious"} and not normalized_note:
            raise InvalidAlertUpdate(
                "A note is required to close or confirm an alert."
            )
        previous = alert.status
        changed = previous != status
        if not changed and not normalized_note:
            return {"alert_id": alert_id, "status": previous, "changed": False}
        self._repository.save_status_event(alert, status, normalized_note)
        return {"alert_id": alert_id, "status": alert.status, "changed": changed}
