"""Customer data view log (K6; BDDK Information Systems Regulation art. 13).

Every response that returns a customer's personal data writes a
``customer.viewed`` audit row first. Repeated views of the same customer by the
same user within 30 minutes do not add rows (react-query refetches would
otherwise flood the log). If the row cannot be written, the data must not be
returned: callers translate CustomerViewLogFailed into HTTP 503.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models import AuditLog


VIEW_DEDUP_WINDOW = timedelta(minutes=30)
VIEW_LOG_FAILED_DETAIL = "Could not record the customer data access."


class CustomerViewLogFailed(Exception):
    pass


def log_customer_views(
    session: Session, actor_id: int, customer_nos: Iterable[str | None], source: str
) -> None:
    numbers = sorted({number for number in customer_nos if number})
    if not numbers:
        return
    try:
        since = datetime.now() - VIEW_DEDUP_WINDOW
        recent = set(
            session.scalars(
                select(AuditLog.entity_id).where(
                    AuditLog.action == "customer.viewed",
                    AuditLog.actor_id == actor_id,
                    AuditLog.entity_type == "customer",
                    AuditLog.entity_id.in_(numbers),
                    AuditLog.created_at >= since,
                )
            )
        )
        for number in numbers:
            if number not in recent:
                session.add(
                    AuditLog(
                        actor_id=actor_id,
                        action="customer.viewed",
                        entity_type="customer",
                        entity_id=number,
                        details={"source": source},
                    )
                )
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise CustomerViewLogFailed(VIEW_LOG_FAILED_DETAIL) from exc
