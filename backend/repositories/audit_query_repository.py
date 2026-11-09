from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import Text, and_, case, cast, func, select
from sqlalchemy.orm import Session

from backend.models import AppRole, AppUser, AuditLog

# One detection run can raise many alerts at once (R17). Each alert keeps its own
# row, but the list shows a run's raises as a single event.
GROUPED_ACTION = "alert.severity_raised"


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
    ) -> tuple[int, list[tuple[AuditLog, str | None, str | None, list[AuditLog]]]]:
        """Newest first. The last value of a row is the run's other raises: every
        alert of a grouped event, or empty for an ordinary one-row event."""
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
        run_id = AuditLog.details["run_id"].astext
        group_key = case(
            (and_(AuditLog.action == GROUPED_ACTION, run_id.is_not(None)), run_id),
            else_=cast(AuditLog.audit_id, Text),
        )
        # Each group is represented by its newest row, so paging counts events
        # as the screen shows them.
        groups = (
            select(func.max(AuditLog.audit_id).label("audit_id"))
            .where(*conditions)
            .group_by(group_key)
            .subquery()
        )
        total = int(self._session.scalar(select(func.count()).select_from(groups)) or 0)
        rows = self._session.execute(
            select(AuditLog, AppUser.username, AppRole.role_code)
            .join(groups, groups.c.audit_id == AuditLog.audit_id)
            .outerjoin(AppUser, AppUser.user_id == AuditLog.actor_id)
            .outerjoin(AppRole, AppRole.role_id == AppUser.role_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
            .offset(offset)
            .limit(limit)
        ).all()

        run_ids = {
            row[0].details["run_id"]
            for row in rows
            if row[0].action == GROUPED_ACTION and "run_id" in row[0].details
        }
        members: dict[str, list[AuditLog]] = {}
        if run_ids:
            for event in self._session.scalars(
                select(AuditLog)
                .where(*conditions, AuditLog.action == GROUPED_ACTION, run_id.in_(run_ids))
                .order_by(AuditLog.audit_id)
            ):
                members.setdefault(event.details["run_id"], []).append(event)

        def grouped_with(event: AuditLog) -> list[AuditLog]:
            if event.action != GROUPED_ACTION:
                return []
            group = members.get(event.details.get("run_id"), [])
            return group if len(group) > 1 else []

        return total, [(row[0], row[1], row[2], grouped_with(row[0])) for row in rows]
