from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from typing import Any

from sqlalchemy import func, select, union
from sqlalchemy.orm import Session, joinedload

from backend.repositories.customer_view_log import log_customer_views
from backend.models import (
    Account,
    AlertTransaction,
    Customer,
    Transaction,
)


@dataclass(frozen=True)
class TransactionFilters:
    date_from: date | None = None
    date_to: date | None = None
    customer_no: str | None = None
    account_no: str | None = None
    direction: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    offset: int = 0
    limit: int = 200


class SqlAlchemyTransactionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _base_query():
        return (
            select(Transaction)
            .options(
                joinedload(Transaction.sender_account).joinedload(Account.customer),
                joinedload(Transaction.receiver_account).joinedload(Account.customer),
            )
            .where(Transaction.is_active)
        )

    @staticmethod
    def _focus_accounts(filters: TransactionFilters):
        if not (filters.customer_no or filters.account_no):
            return None
        account_ids = select(Account.account_id).where(Account.is_active)
        if filters.customer_no:
            account_ids = account_ids.join(Account.customer).where(
                Customer.customer_no == filters.customer_no
            )
        if filters.account_no:
            account_ids = account_ids.where(Account.account_no == filters.account_no)
        return account_ids

    @classmethod
    def _conditions(cls, filters: TransactionFilters) -> list:
        conditions: list = [Transaction.is_active]
        if filters.date_from:
            conditions.append(
                Transaction.tx_time >= datetime.combine(filters.date_from, time.min)
            )
        if filters.date_to:
            conditions.append(
                Transaction.tx_time
                < datetime.combine(filters.date_to + timedelta(days=1), time.min)
            )
        account_ids = cls._focus_accounts(filters)
        if account_ids is not None:
            conditions.append(
                (Transaction.sender_account_id.in_(account_ids))
                | (Transaction.receiver_account_id.in_(account_ids))
            )
            if filters.direction == "incoming":
                conditions.append(Transaction.receiver_account_id.in_(account_ids))
            elif filters.direction == "outgoing":
                conditions.append(Transaction.sender_account_id.in_(account_ids))
        if filters.min_amount is not None:
            conditions.append(Transaction.amount >= filters.min_amount)
        if filters.max_amount is not None:
            conditions.append(Transaction.amount <= filters.max_amount)
        return conditions

    def list_transactions(
        self, filters: TransactionFilters
    ) -> tuple[int, list[Transaction], set[int]]:
        query = self._base_query().where(*self._conditions(filters))
        total = int(
            self._session.scalar(select(func.count()).select_from(query.subquery()))
            or 0
        )
        transactions = list(
            self._session.scalars(
                query.order_by(
                    Transaction.tx_time.desc(),
                    Transaction.transaction_id.desc(),
                )
                .offset(filters.offset)
                .limit(filters.limit)
            ).unique()
        )
        transaction_ids = [transaction.transaction_id for transaction in transactions]
        linked_ids = (
            set(
                self._session.scalars(
                    select(AlertTransaction.transaction_id).where(
                        AlertTransaction.transaction_id.in_(transaction_ids)
                    )
                ).all()
            )
            if transaction_ids
            else set()
        )
        return total, transactions, linked_ids

    def account_owner_numbers(self, account_no: str) -> list[str]:
        return list(
            self._session.scalars(
                select(Customer.customer_no)
                .join(Account, Account.customer_id == Customer.customer_id)
                .where(Account.account_no == account_no)
            )
        )

    def log_customer_views(self, actor_id: int, customer_nos: list[str], source: str) -> None:
        log_customer_views(self._session, actor_id, customer_nos, source)

    def summary(self, filters: TransactionFilters, route_limit: int) -> dict[str, Any]:
        """Totals, timeline and flow routes for the filtered transactions (K12).

        Computed with GROUP BY over every matching row; no transaction row and no
        customer name is returned.
        """
        filtered = (
            select(
                Transaction.transaction_id,
                Transaction.sender_account_id,
                Transaction.receiver_account_id,
                Transaction.amount,
                Transaction.currency,
                Transaction.tx_time,
            )
            .where(*self._conditions(filters))
            .cte("filtered")
        )
        focus = self._focus_accounts(filters)
        focus_ids = set(self._session.scalars(focus)) if focus is not None else None
        totals = self._session.execute(
            select(
                func.count(),
                func.min(filtered.c.tx_time),
                func.max(filtered.c.tx_time),
            ).select_from(filtered)
        ).one()
        senders = select(filtered.c.sender_account_id.label("account_id"))
        receivers = select(filtered.c.receiver_account_id.label("account_id"))
        accounts = union(senders, receivers).subquery()
        account_count = int(
            self._session.scalar(select(func.count()).select_from(accounts)) or 0
        )
        by_currency_rows = self._session.execute(
            select(
                filtered.c.currency,
                func.sum(filtered.c.amount),
                func.sum(filtered.c.amount).filter(
                    filtered.c.receiver_account_id.in_(focus_ids or [-1])
                ),
                func.sum(filtered.c.amount).filter(
                    filtered.c.sender_account_id.in_(focus_ids or [-1])
                ),
                func.count(),
                func.count().filter(filtered.c.receiver_account_id.in_(focus_ids or [-1])),
                func.count().filter(filtered.c.sender_account_id.in_(focus_ids or [-1])),
            )
            .group_by(filtered.c.currency)
            .order_by(filtered.c.currency)
        ).all()
        first, last = totals[1], totals[2]
        span_days = (
            (filters.date_to or (last.date() if last else date.today()))
            - (filters.date_from or (first.date() if first else date.today()))
        ).days
        granularity = "day" if span_days <= 92 else "week"
        bucket = func.date_trunc(granularity, filtered.c.tx_time)
        timeline = self._session.execute(
            select(bucket, func.count()).group_by(bucket).order_by(bucket)
        ).all()
        linked = (
            select(AlertTransaction.transaction_id).distinct().subquery()
        )
        route_amount = func.sum(filtered.c.amount)
        route_rows = self._session.execute(
            select(
                filtered.c.sender_account_id,
                filtered.c.receiver_account_id,
                filtered.c.currency,
                func.count(),
                route_amount,
                func.count(linked.c.transaction_id),
            )
            .outerjoin(linked, linked.c.transaction_id == filtered.c.transaction_id)
            .group_by(
                filtered.c.sender_account_id,
                filtered.c.receiver_account_id,
                filtered.c.currency,
            )
            .order_by(route_amount.desc(), filtered.c.sender_account_id, filtered.c.receiver_account_id)
        ).all()
        shown = route_rows[:route_limit]
        account_numbers = dict(
            self._session.execute(
                select(Account.account_id, Account.account_no).where(
                    Account.account_id.in_(
                        {row[0] for row in shown} | {row[1] for row in shown}
                    )
                )
            ).all()
        ) if shown else {}
        rest = route_rows[route_limit:]
        return {
            "transfer_count": int(totals[0] or 0),
            "account_count": account_count,
            "focus_account_ids": focus_ids,
            "by_currency": [
                {
                    "currency": row[0],
                    "total": row[1],
                    "incoming": row[2] if focus_ids is not None else None,
                    "outgoing": row[3] if focus_ids is not None else None,
                    "count": int(row[4]),
                    "incoming_count": int(row[5]) if focus_ids is not None else None,
                    "outgoing_count": int(row[6]) if focus_ids is not None else None,
                }
                for row in by_currency_rows
            ],
            "granularity": granularity,
            "timeline": [(row[0].date(), int(row[1])) for row in timeline],
            "routes": [
                {
                    "sender_account_id": row[0],
                    "receiver_account_id": row[1],
                    "sender_account_no": account_numbers.get(row[0], ""),
                    "receiver_account_no": account_numbers.get(row[1], ""),
                    "currency": row[2],
                    "count": int(row[3]),
                    "amount": row[4],
                    "alert_linked": int(row[5]),
                }
                for row in shown
            ],
            "other_routes": {
                "route_count": len(rest),
                "count": sum(int(row[3]) for row in rest),
            },
        }
