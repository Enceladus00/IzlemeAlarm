"""Customer and account lists (customer:view).

View logging (K6) follows one rule: a response that shows more than a
customer's name and number is logged.
* GET /customers (name, number, type, risk, counts): not logged, like the alert lists.
* GET /accounts (full account numbers): every customer on the page is logged.
* GET /customers/{no} (full profile): the customer is logged.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from backend.repositories.customer_repository import (
    AccountFilters,
    CustomerFilters,
    SqlAlchemyCustomerRepository,
)


MSG_CUSTOMER_NOT_FOUND = "Customer not found."
# E12: warn when a month's TRY inflow or outflow reaches this multiple of monthly income.
INCOME_WARNING_MULTIPLE = Decimal("3")
INCOME_CURRENCY = "TRY"
COUNTERPARTY_LIMIT = 10
# "YENİ" counterparty: no transaction with the customer in the 12 months before the period.
NEW_COUNTERPARTY_LOOKBACK_DAYS = 365


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

    def analysis(self, customer_no: str, days: int, actor_id: int) -> dict[str, Any]:
        """E12 customer analysis for the last `days` days (including today)."""
        customer = self._repository.get_customer(customer_no)
        if customer is None:
            raise CustomerNotFound(MSG_CUSTOMER_NOT_FOUND)
        today = date.today()
        date_from = today - timedelta(days=days - 1)
        since = datetime.combine(date_from, time.min)
        until = datetime.combine(today + timedelta(days=1), time.min)
        data = self._repository.customer_analysis(
            customer.customer_id,
            since,
            until,
            since - timedelta(days=NEW_COUNTERPARTY_LOOKBACK_DAYS),
        )
        monthly = [
            {
                "month": row["month"].strftime("%Y-%m"),
                "currency": row["currency"],
                "incoming": row["incoming"],
                "outgoing": row["outgoing"],
            }
            for row in data["monthly"]
        ]
        income = customer.monthly_income
        peak: dict[str, Any] | None = None
        for row in monthly:
            if row["currency"] != INCOME_CURRENCY:
                continue
            for direction in ("incoming", "outgoing"):
                if row[direction] > 0 and (peak is None or row[direction] > peak["amount"]):
                    peak = {"month": row["month"], "direction": direction, "amount": row[direction]}
        ratio = (
            (peak["amount"] / income).quantize(Decimal("0.1"))
            if peak and income and income > 0
            else None
        )
        counterparties: dict[str, list[dict[str, Any]]] = {"incoming": [], "outgoing": []}
        for row in data["counterparties"]:
            bucket = counterparties["incoming" if row["direction"] == "in" else "outgoing"]
            if len(bucket) < COUNTERPARTY_LIMIT:
                bucket.append(
                    {
                        "account_no": row["account_no"],
                        "customer_no": row["customer_no"],
                        "customer_name": row["customer_name"],
                        "currency": row["currency"],
                        "count": int(row["count"]),
                        "amount": row["amount"],
                        "is_new": bool(row["is_new"]),
                    }
                )
        self._repository.log_customer_views(actor_id, [customer.customer_no], "customer_analysis")
        return {
            "customer_no": customer.customer_no,
            "days": days,
            "date_from": date_from,
            "date_to": today,
            "monthly": monthly,
            "income_check": {
                "monthly_income": income,
                "currency": INCOME_CURRENCY,
                "peak_month": peak["month"] if peak else None,
                "peak_direction": peak["direction"] if peak else None,
                "peak_amount": peak["amount"] if peak else None,
                "ratio": ratio,
                "threshold": INCOME_WARNING_MULTIPLE,
                "exceeded": ratio is not None and ratio >= INCOME_WARNING_MULTIPLE,
            },
            "counterparties": counterparties,
        }

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
