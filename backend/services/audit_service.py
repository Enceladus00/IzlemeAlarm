from typing import Any

from backend.repositories.audit_query_repository import SqlAlchemyAuditQueryRepository


class AuditService:
    def __init__(self, repository: SqlAlchemyAuditQueryRepository) -> None:
        self._repository = repository

    def list_events(self, offset: int, limit: int) -> dict[str, Any]:
        total, events = self._repository.list_events(offset, limit)
        return {
            "total": total,
            "items": [
                {
                    "audit_id": event.audit_id,
                    "actor_id": event.actor_id,
                    "action": event.action,
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "details": event.details,
                    "created_at": event.created_at,
                }
                for event in events
            ],
        }
