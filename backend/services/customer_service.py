"""Customer and account lists (customer:view).

View logging (K6) follows one rule: a response that shows more than a
customer's name and number is logged.
* GET /customers (name, number, type, risk, counts): not logged, like the alert lists.
* GET /accounts (full account numbers): every customer on the page is logged.
* GET /customers/{no} (full profile): the customer is logged.
"""

from typing import Any

from backend.repositories.customer_repository import (
    AccountFilters,
    CustomerFilters,
    SqlAlchemyCustomerRepository,
)


MSG_CUSTOMER_NOT_FOUND = "Customer not found."


class CustomerNotFound(LookupError):
    pass


class CustomerService:
    def __init__(self, repository: SqlAlchemyCustomerRepository) -> None:
        self._repository = repository

    def list_customers(self, filters: CustomerFilters) -> dict[str, Any]:
        total, rows = self._repository.list_customers(filters)
        return {
            "total": total,
            "items": [
                {
                    "customer_no": row["customer"].customer_no,
                    "full_name": row["customer"].full_name,
                    "customer_type": row["customer"].customer_type,
                    "risk_level": row["customer"].risk_level,
                    "is_active": row["customer"].is_active,
                    "account_count": row["account_count"],
                    "open_alert_count": row["open_alert_count"],
                }
                for row in rows
            ],
        }

    def get_customer(self, customer_no: str, actor_id: int) -> dict[str, Any]:
        customer = self._repository.get_customer(customer_no)
        if customer is None:
            raise CustomerNotFound(MSG_CUSTOMER_NOT_FOUND)
        accounts = sorted(customer.accounts, key=lambda account: account.account_no)
        counts = self._repository.account_transaction_counts([a.account_id for a in accounts])
        alerts = self._repository.alert_counts(customer.customer_id)
        result = {
            "customer_no": customer.customer_no,
            "full_name": customer.full_name,
            "customer_type": customer.customer_type,
            "occupation": customer.occupation,
            "monthly_income": customer.monthly_income,
            "risk_level": customer.risk_level,
            "is_active": customer.is_active,
            "created_at": customer.created_at,
            "accounts": [
                {
                    "account_no": account.account_no,
                    "currency": account.currency,
                    "account_type": account.account_type,
                    "is_active": account.is_active,
                    "opened_at": account.opened_at,
                    "transaction_count": counts.get(account.account_id, 0),
                }
                for account in accounts
            ],
            "alerts": {
                "open": alerts.get("new", 0) + alerts.get("in_review", 0),
                "total": sum(alerts.values()),
                "by_status": alerts,
            },
        }
        self._repository.log_customer_views(actor_id, [customer.customer_no], "customer_profile")
        return result

    def list_accounts(self, filters: AccountFilters, actor_id: int) -> dict[str, Any]:
        total, rows = self._repository.list_accounts(filters)
        items = [
            {
                "account_no": account.account_no,
                "customer_no": customer.customer_no,
                "customer_name": customer.full_name,
                "currency": account.currency,
                "account_type": account.account_type,
                "is_active": account.is_active,
                "opened_at": account.opened_at,
            }
            for account, customer in rows
        ]
        self._repository.log_customer_views(
            actor_id, sorted({item["customer_no"] for item in items}), "account_list"
        )
        return {"total": total, "items": items}
