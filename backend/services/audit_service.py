from typing import Any

from backend.repositories.audit_query_repository import (
    AuditFilters,
    SqlAlchemyAuditQueryRepository,
)

REDACTED = "[gizli]"


def redact(event_action: str, entity_id: str | None, details: dict[str, Any], permissions: frozenset[str]) -> tuple[str | None, dict[str, Any]]:
    """K13: audit readers without alert/customer access (the administrator) see that
    something happened and who did it, but not the alert's free-text notes or which
    customer's data was viewed."""
    details = dict(details or {})
    if "alert:view" not in permissions and event_action.startswith("alert.") and "note" in details:
        details["note"] = REDACTED
    if "customer:view" not in permissions and event_action == "customer.viewed":
        entity_id = REDACTED
    return entity_id, details


class AuditService:
    def __init__(self, repository: SqlAlchemyAuditQueryRepository) -> None:
        self._repository = repository

    def list_events(
        self,
        offset: int,
        limit: int,
        filters: AuditFilters | None = None,
        permissions: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        total, rows = self._repository.list_events(offset, limit, filters)
        items = []
        for event, actor_name, actor_role in rows:
            entity_id, details = redact(event.action, event.entity_id, event.details, permissions)
            items.append(
                {
                    "audit_id": event.audit_id,
                    "actor_id": event.actor_id,
                    "actor_name": actor_name,
                    "actor_role": actor_role,
                    "action": event.action,
                    "entity_type": event.entity_type,
                    "entity_id": entity_id,
                    "details": details,
                    "created_at": event.created_at,
                }
            )
        return {"total": total, "items": items}
