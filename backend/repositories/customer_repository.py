from dataclasses import dataclass
from typing import Any

from datetime import datetime

from sqlalchemy import func, or_, select, text
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

    def customer_analysis(
        self, customer_id: int, since: datetime, until: datetime, history_since: datetime
    ) -> dict[str, Any]:
        """E12: monthly in/out per currency and counterparties in [since, until).

        Transfers between the customer's own accounts are left out. A counterparty
        is new when it had no transaction with the customer in [history_since, since).
        """
        params = {"cid": customer_id, "since": since, "until": until, "history_since": history_since}
        monthly = self._session.execute(
            text(
                """
                WITH own AS (SELECT account_id FROM account WHERE customer_id = :cid),
                tx AS (
                    SELECT t.tx_time, t.currency, t.amount,
                           t.receiver_account_id IN (SELECT account_id FROM own) AS to_me,
                           t.sender_account_id IN (SELECT account_id FROM own) AS from_me
                    FROM transaction t
                    WHERE t.is_active AND t.tx_time >= :since AND t.tx_time < :until
                      AND (t.sender_account_id IN (SELECT account_id FROM own)
                           OR t.receiver_account_id IN (SELECT account_id FROM own))
                )
                SELECT date_trunc('month', tx_time)::date AS month, currency,
                       COALESCE(SUM(amount) FILTER (WHERE to_me AND NOT from_me), 0) AS incoming,
                       COALESCE(SUM(amount) FILTER (WHERE from_me AND NOT to_me), 0) AS outgoing
                FROM tx GROUP BY 1, 2 ORDER BY 1, 2
                """
            ),
            params,
        ).mappings().all()
        counterparties = self._session.execute(
            text(
                """
                WITH own AS (SELECT account_id FROM account WHERE customer_id = :cid),
                flows AS (
                    SELECT 'in' AS direction, t.sender_account_id AS other_id, t.currency, t.amount
                    FROM transaction t
                    WHERE t.is_active AND t.tx_time >= :since AND t.tx_time < :until
                      AND t.receiver_account_id IN (SELECT account_id FROM own)
                      AND t.sender_account_id NOT IN (SELECT account_id FROM own)
                    UNION ALL
                    SELECT 'out', t.receiver_account_id, t.currency, t.amount
                    FROM transaction t
                    WHERE t.is_active AND t.tx_time >= :since AND t.tx_time < :until
                      AND t.sender_account_id IN (SELECT account_id FROM own)
                      AND t.receiver_account_id NOT IN (SELECT account_id FROM own)
                )
                SELECT f.direction, a.account_no, c.customer_no, c.full_name AS customer_name,
                       f.currency, COUNT(*) AS count, SUM(f.amount) AS amount,
                       NOT EXISTS (
                           SELECT 1 FROM transaction h
                           WHERE h.is_active AND h.tx_time >= :history_since AND h.tx_time < :since
                             AND ((h.sender_account_id = f.other_id
                                   AND h.receiver_account_id IN (SELECT account_id FROM own))
                               OR (h.receiver_account_id = f.other_id
                                   AND h.sender_account_id IN (SELECT account_id FROM own)))
                       ) AS is_new
                FROM flows f
                JOIN account a ON a.account_id = f.other_id
                JOIN customer c ON c.customer_id = a.customer_id
                GROUP BY f.direction, f.other_id, a.account_no, c.customer_no, c.full_name, f.currency
                ORDER BY f.direction, SUM(f.amount) DESC, a.account_no
                """
            ),
            params,
        ).mappings().all()
        return {
            "monthly": [dict(row) for row in monthly],
            "counterparties": [dict(row) for row in counterparties],
        }

    def log_customer_views(self, actor_id: int, customer_nos: list[str], source: str) -> None:
        log_customer_views(self._session, actor_id, customer_nos, source)
