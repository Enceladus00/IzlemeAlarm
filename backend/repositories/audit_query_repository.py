from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import AuditLog


class SqlAlchemyAuditQueryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_events(self, offset: int, limit: int) -> tuple[int, list[AuditLog]]:
        total = int(
            self._session.scalar(select(func.count()).select_from(AuditLog)) or 0
        )
        events = list(
            self._session.scalars(
                select(AuditLog)
                .order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        return total, events
