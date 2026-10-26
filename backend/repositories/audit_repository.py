from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from backend.database import create_independent_session
from backend.models import AuditLog


class AuditLogRepository:
    def write_event(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        actor_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        session = create_independent_session()
        try:
            session.add(
                AuditLog(
                    actor_id=actor_id,
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    details=details or {},
                )
            )
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()
