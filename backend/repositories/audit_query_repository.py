from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import AppRole, AppUser, AuditLog


@dataclass(frozen=True)
class AuditFilters:
    actor_id: int | None = None
    action: str | None = None
    exclude_action: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class SqlAlchemyAuditQueryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_events(
        self, offset: int, limit: int, filters: AuditFilters | None = None
    ) -> tuple[int, list[tuple[AuditLog, str | None, str | None]]]:
        filters = filters or AuditFilters()
        conditions = []
        if filters.actor_id is not None:
            conditions.append(AuditLog.actor_id == filters.actor_id)
        if filters.action:
            conditions.append(AuditLog.action == filters.action)
        if filters.exclude_action:
            conditions.append(AuditLog.action != filters.exclude_action)
        if filters.entity_type:
            conditions.append(AuditLog.entity_type == filters.entity_type)
        if filters.entity_id:
            conditions.append(AuditLog.entity_id == filters.entity_id)
        if filters.date_from:
            conditions.append(AuditLog.created_at >= datetime.combine(filters.date_from, time.min))
        if filters.date_to:
            conditions.append(
                AuditLog.created_at < datetime.combine(filters.date_to + timedelta(days=1), time.min)
            )
        total = int(
            self._session.scalar(
                select(func.count()).select_from(AuditLog).where(*conditions)
            )
            or 0
        )
        rows = self._session.execute(
            select(AuditLog, AppUser.username, AppRole.role_code)
            .outerjoin(AppUser, AppUser.user_id == AuditLog.actor_id)
            .outerjoin(AppRole, AppRole.role_id == AppUser.role_id)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return total, [(row[0], row[1], row[2]) for row in rows]
