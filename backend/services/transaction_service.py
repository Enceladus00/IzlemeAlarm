from datetime import date
from decimal import Decimal
from typing import Any

from backend.models import Customer, Transaction
from backend.repositories.transaction_repository import (
    SqlAlchemyTransactionRepository,
    TransactionFilters,
)


class InvalidTransactionFilters(ValueError):
    pass


class CustomerNotFound(LookupError):
    pass


class TransactionService:
    def __init__(self, repository: SqlAlchemyTransactionRepository) -> None:
        self._repository = repository

    @staticmethod
    def transaction_view(transaction: Transaction) -> dict[str, Any]:
        return {
            "transaction_id": transaction.transaction_id,
            "transaction_no": transaction.transaction_no,
            "amount": transaction.amount,
            "currency": transaction.currency,
            "tx_time": transaction.tx_time,
            "country_code": transaction.country_code,
            "channel": transaction.channel,
            "sender_account_no": transaction.sender_account.account_no,
            "sender_customer_no": transaction.sender_account.customer.customer_no,
            "sender_customer_name": transaction.sender_account.customer.full_name,
            "receiver_account_no": transaction.receiver_account.account_no,
            "receiver_customer_no": transaction.receiver_account.customer.customer_no,
            "receiver_customer_name": transaction.receiver_account.customer.full_name,
        }

    def list_transactions(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        customer_no: str | None = None,
        account_no: str | None = None,
        direction: str | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        if date_from and date_to and date_from > date_to:
            raise InvalidTransactionFilters("date_from must not be after date_to.")
        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            raise InvalidTransactionFilters("min_amount must not exceed max_amount.")
        if direction and not (customer_no or account_no):
            raise InvalidTransactionFilters(
                "customer_no or account_no is required when filtering by direction."
            )
        filters = TransactionFilters(
            date_from=date_from,
            date_to=date_to,
            customer_no=customer_no,
            account_no=account_no,
            direction=direction,
            min_amount=min_amount,
            max_amount=max_amount,
            offset=offset,
            limit=limit,
        )
        total, transactions, linked_ids = self._repository.list_transactions(filters)
        return {
            "total": total,
            "items": [
                {
                    **self.transaction_view(transaction),
                    "alert_linked": transaction.transaction_id in linked_ids,
                }
                for transaction in transactions
            ],
        }

    def customer_history(self, customer_no: str, limit: int) -> dict[str, Any]:
        customer: Customer | None = self._repository.get_customer(customer_no)
        if customer is None:
            raise CustomerNotFound("Customer not found.")
        transactions = self._repository.list_customer_transactions(customer, limit)
        return {
            "customer_no": customer.customer_no,
            "customer_name": customer.full_name,
            "items": [self.transaction_view(transaction) for transaction in transactions],
        }
