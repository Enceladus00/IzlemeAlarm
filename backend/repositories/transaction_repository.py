from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

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

    def list_transactions(
        self, filters: TransactionFilters
    ) -> tuple[int, list[Transaction], set[int]]:
        query = self._base_query()
        if filters.date_from:
            query = query.where(
                Transaction.tx_time
                >= datetime.combine(filters.date_from, time.min)
            )
        if filters.date_to:
            query = query.where(
                Transaction.tx_time
                < datetime.combine(filters.date_to + timedelta(days=1), time.min)
            )
        if filters.customer_no or filters.account_no:
            account_ids = select(Account.account_id).where(Account.is_active)
            if filters.customer_no:
                account_ids = account_ids.join(Account.customer).where(
                    Customer.customer_no == filters.customer_no
                )
            if filters.account_no:
                account_ids = account_ids.where(
                    Account.account_no == filters.account_no
                )
            query = query.where(
                (Transaction.sender_account_id.in_(account_ids))
                | (Transaction.receiver_account_id.in_(account_ids))
            )
            if filters.direction == "incoming":
                query = query.where(Transaction.receiver_account_id.in_(account_ids))
            elif filters.direction == "outgoing":
                query = query.where(Transaction.sender_account_id.in_(account_ids))
        if filters.min_amount is not None:
            query = query.where(Transaction.amount >= filters.min_amount)
        if filters.max_amount is not None:
            query = query.where(Transaction.amount <= filters.max_amount)
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

    def get_customer(self, customer_no: str) -> Customer | None:
        return self._session.scalar(
            select(Customer).where(
                Customer.customer_no == customer_no,
                Customer.is_active,
            )
        )

    def list_customer_transactions(
        self, customer: Customer, limit: int
    ) -> list[Transaction]:
        account_ids = select(Account.account_id).where(
            Account.customer_id == customer.customer_id,
            Account.is_active,
        )
        return list(
            self._session.scalars(
                self._base_query()
                .where(
                    (Transaction.sender_account_id.in_(account_ids))
                    | (Transaction.receiver_account_id.in_(account_ids))
                )
                .order_by(
                    Transaction.tx_time.desc(),
                    Transaction.transaction_id.desc(),
                )
                .limit(limit)
            ).unique()
        )
