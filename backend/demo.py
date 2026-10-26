from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Account, Customer, MonitoringRule, Transaction


RULES = [
    (
        "R1",
        "Repeated near-limit transactions",
        "At least two same-currency customer transactions in the near-limit range within the configured window.",
        {
            "amount_limit": 10000,
            "proximity_percent": 10,
            "transaction_count": 2,
            "window_minutes": 60,
        },
    ),
    (
        "R2",
        "Rapid in-and-out transfers",
        "Outgoing transfers are at least the configured fraction of incoming transfers within one rolling window.",
        {"outflow_ratio": 0.8, "window_minutes": 60},
    ),
    (
        "R3",
        "Unusual transaction amount",
        "Outgoing amount exceeds the multiplier times the average of the five preceding customer transactions.",
        {"average_multiplier": 3, "minimum_history_count": 5},
    ),
    (
        "R4",
        "Risky country (demo)",
        "Demo-only country match. Country codes are examples, not a real risk list.",
        {"countries": ["TR", "IL", "US"], "enabled": True},
    ),
]


def seed_demo_data(db: Session) -> dict[str, int]:
    for code, name, description, thresholds in RULES:
        rule = db.scalar(
            select(MonitoringRule).where(MonitoringRule.rule_code == code)
        )
        if rule is None:
            db.add(
                MonitoringRule(
                    rule_code=code,
                    name=name,
                    description=description,
                    thresholds=thresholds,
                    is_active=True,
                )
            )
        elif code == "R4" and rule.thresholds == {
            "countries": [],
            "enabled": False,
        }:
            rule.thresholds = {**thresholds, "enabled": True}
    db.flush()

    customers = []
    for index in range(1, 11):
        customer = db.scalar(
            select(Customer).where(Customer.customer_no == f"DEMO-{index:03d}")
        )
        if customer is None:
            customer = Customer(
                customer_no=f"DEMO-{index:03d}",
                full_name=f"Demo Customer {index:02d}",
                customer_type="person",
                occupation="Demo",
                monthly_income=Decimal("50000.00"),
                risk_level="low",
            )
            db.add(customer)
            db.flush()
        customers.append(customer)

    accounts = []
    for index, customer in enumerate(customers, 1):
        account = db.scalar(
            select(Account).where(Account.account_no == f"DEMO-ACC-{index:03d}")
        )
        if account is None:
            account = Account(
                account_no=f"DEMO-ACC-{index:03d}",
                customer_id=customer.customer_id,
                currency="TRY",
                account_type="current",
                opened_at=datetime(2025, 1, 1).date(),
            )
            db.add(account)
            db.flush()
        accounts.append(account)

    existing = db.scalar(
        select(Transaction.transaction_id).where(
            Transaction.transaction_no.like("DEMO-TX-%")
        ).limit(1)
    )
    if not existing:
        base = datetime(2026, 1, 1, 9, 0)
        specs: list[tuple[int, int, str, str, int, str]] = []
        for minute, amount in enumerate([100, 120, 90, 110, 80]):
            specs.append((2, 3, str(amount), "TR", minute, "mobile"))
        specs.append((2, 3, "400", "TR", 10, "mobile"))
        specs.extend(
            [
                (1, 4, "9500", "TR", 20, "internet"),
                (1, 5, "9600", "TR", 45, "internet"),
                (6, 7, "1000", "US", 30, "mobile"),
                (7, 8, "850", "US", 50, "mobile"),
                (4, 9, "250", "IL", 60, "branch"),
                (5, 9, "300", "US", 75, "atm"),
                (6, 1, "150", "US", 90, "mobile"),
                (8, 2, "200", "US", 105, "internet"),
                (9, 3, "180", "US", 120, "branch"),
                (10, 4, "220", "US", 135, "atm"),
                (3, 5, "175", "US", 150, "mobile"),
                (7, 6, "125", "US", 165, "internet"),
                (8, 10, "275", "US", 180, "branch"),
                (9, 1, "325", "US", 195, "atm"),
            ]
        )
        for index, (sender, receiver, amount, country, minute, channel) in enumerate(
            specs, 1
        ):
            db.add(
                Transaction(
                    transaction_no=f"DEMO-TX-{index:03d}",
                    sender_account_id=accounts[sender - 1].account_id,
                    receiver_account_id=accounts[receiver - 1].account_id,
                    amount=Decimal(amount),
                    currency="TRY",
                    tx_time=base + timedelta(minutes=minute),
                    channel=channel,
                    country_code=country,
                )
            )

    db.commit()
    return {
        "customers": 10,
        "accounts": 10,
        "transactions": 20,
        "rules": len(RULES),
    }
