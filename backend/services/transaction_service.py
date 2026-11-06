import hashlib
import hmac
from datetime import date
from decimal import Decimal
from typing import Any

from backend.models import Customer, Transaction
from backend.repositories.transaction_repository import (
    SqlAlchemyTransactionRepository,
    TransactionFilters,
)
from backend.security import get_jwt_secret
from backend.services.masking import mask_name


class InvalidTransactionFilters(ValueError):
    pass


ROUTE_LIMIT = 200


def make_account_ref(account_id: int) -> str:
    """Opaque, signed handle for a counterparty account. The browser only sees
    masked labels (K4), so the network graph expands a node with this instead
    of the account number; the signature stops clients from probing ids."""
    digest = hmac.new(get_jwt_secret().encode(), f"account:{account_id}".encode(), hashlib.sha256).hexdigest()
    return f"{account_id}.{digest[:24]}"


def resolve_account_ref(ref: str) -> int:
    account_id, _, _ = ref.partition(".")
    if not account_id.isdigit() or not hmac.compare_digest(make_account_ref(int(account_id)), ref):
        raise InvalidTransactionFilters("Invalid account reference.")
    return int(account_id)


def mask_route_account(account_no: str) -> str:
    """'TR..4410' style label: the flow diagram needs to tell accounts apart, not
    the full account number (K12, KVKK data minimisation)."""
    value = account_no.strip()
    if len(value) <= 6:
        return value
    return f"{value[:2]}…{value[-4:]}"


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

    def summary(
        self,
        *,
        actor_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        customer_no: str | None = None,
        account_no: str | None = None,
        direction: str | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        account_ref: str | None = None,
    ) -> dict[str, Any]:
        """K12: server-side totals over every matching transaction."""
        if account_ref:
            if customer_no or account_no:
                raise InvalidTransactionFilters("Use either account_ref or customer_no/account_no.")
            account_no = self._repository.account_no_for_id(resolve_account_ref(account_ref))
            if account_no is None:
                raise InvalidTransactionFilters("Invalid account reference.")
        self._validate(date_from, date_to, customer_no, account_no, direction, min_amount, max_amount)
        filters = TransactionFilters(
            date_from=date_from,
            date_to=date_to,
            customer_no=customer_no,
            account_no=account_no,
            direction=direction,
            min_amount=min_amount,
            max_amount=max_amount,
        )
        data = self._repository.summary(filters, ROUTE_LIMIT)
        if actor_id is not None and (customer_no or account_no):
            viewed = [customer_no] if customer_no else self._repository.account_owner_numbers(account_no)
            self._repository.log_customer_views(actor_id, viewed, "transaction_analysis")
        focus = data["focus_account_ids"]
        refs: dict[int, str] = {}

        def _ref(account_id: int) -> str:
            if account_id not in refs:
                refs[account_id] = make_account_ref(account_id)
            return refs[account_id]

        return {
            "transfer_count": data["transfer_count"],
            "account_count": data["account_count"],
            "by_currency": data["by_currency"],
            "timeline": {
                "granularity": data["granularity"],
                "points": [{"date": day, "count": count} for day, count in data["timeline"]],
            },
            "routes": [
                {
                    "sender_account": mask_route_account(route["sender_account_no"]),
                    "receiver_account": mask_route_account(route["receiver_account_no"]),
                    "sender_is_focus": focus is not None and route["sender_account_id"] in focus,
                    "receiver_is_focus": focus is not None and route["receiver_account_id"] in focus,
                    "currency": route["currency"],
                    "count": route["count"],
                    "amount": route["amount"],
                    "alert_linked": route["alert_linked"],
                    # Masked owner names (K4): enough to tell counterparties apart.
                    "sender_ref": _ref(route["sender_account_id"]),
                    "receiver_ref": _ref(route["receiver_account_id"]),
                    "sender_label": mask_name(*route["sender_owner"]),
                    "receiver_label": mask_name(*route["receiver_owner"]),
                    "alert_rules": route["alert_rules"],
                }
                for route in data["routes"]
            ],
            "other_routes": {**data["other_routes"], "by_currency": data["other_routes_amount"]},
            "flow_timeline": data["flow_timeline"],
        }

    @staticmethod
    def _validate(date_from, date_to, customer_no, account_no, direction, min_amount, max_amount) -> None:
        if date_from and date_to and date_from > date_to:
            raise InvalidTransactionFilters("date_from must not be after date_to.")
        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            raise InvalidTransactionFilters("min_amount must not exceed max_amount.")
        if direction and not (customer_no or account_no):
            raise InvalidTransactionFilters(
                "customer_no or account_no is required when filtering by direction."
            )

    def list_transactions(
        self,
        *,
        actor_id: int | None = None,
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
        if actor_id is not None:
            # K6: log whose personal data this response reveals, before returning it.
            if customer_no:
                viewed = [customer_no]
            elif account_no:
                viewed = self._repository.account_owner_numbers(account_no)
            else:
                viewed = sorted(
                    {
                        party.customer.customer_no
                        for transaction in transactions
                        for party in (transaction.sender_account, transaction.receiver_account)
                    }
                )
            self._repository.log_customer_views(actor_id, viewed, "transaction_analysis")
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
