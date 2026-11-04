from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.models import Account, Alert, Customer, Transaction
from backend.repositories.customer_view_log import log_customer_views


OPEN_STATUSES = ("new", "in_review")


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


@dataclass(frozen=True)
class CustomerFilters:
    q: str | None = None
    customer_type: str | None = None
    risk_level: str | None = None
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True)
class AccountFilters:
    q: str | None = None
    customer_no: str | None = None
    currency: str | None = None
    offset: int = 0
    limit: int = 50


class SqlAlchemyCustomerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_customers(self, filters: CustomerFilters) -> tuple[int, list[dict[str, Any]]]:
        conditions = []
        if filters.q:
            pattern = _like(filters.q)
            conditions.append(or_(Customer.full_name.ilike(pattern), Customer.customer_no.ilike(pattern)))
        if filters.customer_type:
            conditions.append(Customer.customer_type == filters.customer_type)
        if filters.risk_level:
            conditions.append(Customer.risk_level == filters.risk_level)
        total = int(
            self._session.scalar(select(func.count()).select_from(Customer).where(*conditions)) or 0
        )
        account_count = (
            select(func.count())
            .where(Account.customer_id == Customer.customer_id, Account.is_active)
            .correlate(Customer)
            .scalar_subquery()
        )
        open_alerts = (
            select(func.count())
            .where(Alert.customer_id == Customer.customer_id, Alert.status.in_(OPEN_STATUSES))
            .correlate(Customer)
            .scalar_subquery()
        )
        rows = self._session.execute(
            select(Customer, account_count, open_alerts)
            .where(*conditions)
            .order_by(Customer.customer_no)
            .offset(filters.offset)
            .limit(filters.limit)
        ).all()
        return total, [
            {"customer": row[0], "account_count": int(row[1]), "open_alert_count": int(row[2])}
            for row in rows
        ]

    def get_customer(self, customer_no: str) -> Customer | None:
        return self._session.scalar(
            select(Customer)
            .where(Customer.customer_no == customer_no)
            .options(selectinload(Customer.accounts))
        )

    def account_transaction_counts(self, account_ids: list[int]) -> dict[int, int]:
        if not account_ids:
            return {}
        counts: dict[int, int] = {account_id: 0 for account_id in account_ids}
        for column in (Transaction.sender_account_id, Transaction.receiver_account_id):
            for account_id, count in self._session.execute(
                select(column, func.count())
                .where(column.in_(account_ids), Transaction.is_active)
                .group_by(column)
            ).all():
                counts[account_id] += int(count)
        return counts

    def alert_counts(self, customer_id: int) -> dict[str, int]:
        rows = self._session.execute(
            select(Alert.status, func.count()).where(Alert.customer_id == customer_id).group_by(Alert.status)
        ).all()
        return {status: int(count) for status, count in rows}

    def list_accounts(self, filters: AccountFilters) -> tuple[int, list[tuple[Account, Customer]]]:
        conditions = []
        if filters.q:
            pattern = _like(filters.q)
            conditions.append(
                or_(
                    Account.account_no.ilike(pattern),
                    Customer.customer_no.ilike(pattern),
                    Customer.full_name.ilike(pattern),
                )
            )
        if filters.customer_no:
            conditions.append(Customer.customer_no == filters.customer_no)
        if filters.currency:
            conditions.append(Account.currency == filters.currency)
        base = select(Account, Customer).join(Customer, Customer.customer_id == Account.customer_id).where(*conditions)
        total = int(self._session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = self._session.execute(
            base.order_by(Account.account_no).offset(filters.offset).limit(filters.limit)
        ).all()
        return total, [(row[0], row[1]) for row in rows]

    def log_customer_views(self, actor_id: int, customer_nos: list[str], source: str) -> None:
        log_customer_views(self._session, actor_id, customer_nos, source)
