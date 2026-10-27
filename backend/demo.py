from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.detection.registry import load_rule_registry
from backend.detection.parameters import validate_rule_parameters
from backend.models import Account, Customer, MonitoringRule, Transaction


NEW_RULE_WEIGHTS = {"R01": Decimal("1.000"), "R02": Decimal("0.450"), "R03": Decimal("1.000")}
UNSET_THRESHOLDS = {
    "BIREYSEL": {"status": "UNSET", "values": {}},
    "KURUMSAL": {"status": "UNSET", "values": {}},
}
DEMO_RULE_OVERRIDES = {
    "R01": {
        "BIREYSEL": {
            "status": "PROVISIONAL",
            "values": {
                "limits": {"TRY": "10000"},
                "x_esik": 1,
                "x_kesin": 3,
                "minimum_income_ratio": "0.01",
                "income_currency": "TRY",
            },
        },
        "KURUMSAL": {
            "status": "PROVISIONAL",
            "values": {
                "limits": {"TRY": "10000"},
                "x_esik": 1,
                "x_kesin": 3,
                "minimum_income_ratio": "0.01",
                "income_currency": "TRY",
            },
        },
    },
    "R02": {
        "BIREYSEL": {
            "status": "PROVISIONAL",
            "values": {"limits": {"TRY": "15000"}},
        },
        "KURUMSAL": {
            "status": "PROVISIONAL",
            "values": {"limits": {"TRY": "15000"}},
        },
    },
    "R03": {
        "BIREYSEL": {
            "status": "PROVISIONAL",
            "values": {
                "limits": {"TRY": "1000"},
                "x_esik": 1,
                "x_kesin": 3,
                "cash_channels": ["atm", "branch"],
            },
        },
        "KURUMSAL": {
            "status": "PROVISIONAL",
            "values": {
                "limits": {"TRY": "1000"},
                "x_esik": 1,
                "x_kesin": 3,
                "cash_channels": ["atm", "branch"],
            },
        },
    },
}


def seed_demo_data(
    db: Session, *, as_of: datetime | None = None
) -> dict[str, Any]:
    run_as_of = as_of or datetime.now()
    registry = load_rule_registry()
    for code, weight in NEW_RULE_WEIGHTS.items():
        definition = registry[code].definition
        thresholds = validate_rule_parameters(
            code, definition.parameter_model, UNSET_THRESHOLDS
        )
        rule = db.scalar(
            select(MonitoringRule).where(MonitoringRule.rule_code == code)
        )
        if rule is None:
            db.add(
                MonitoringRule(
                    rule_code=code,
                    name=definition.name,
                    description=definition.description,
                    thresholds=thresholds,
                    is_active=False,
                    weight=weight,
                )
            )
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
                customer_type="BIREYSEL" if index <= 3 else "KURUMSAL",
                occupation="Demo",
                monthly_income=Decimal("50000.00"),
                risk_level="low",
            )
            db.add(customer)
            db.flush()
        customer.customer_type = "BIREYSEL" if index <= 3 else "KURUMSAL"
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

    demo_transactions = (
        ("DEMO-R01-001", 1, 4, "9500", 70, "internet"),
        ("DEMO-R01-002", 1, 5, "9800", 40, "internet"),
        ("DEMO-R02-001", 2, 1, "16000", 30, "mobile"),
        ("DEMO-R03-001", 4, 3, "500", 25, "atm"),
        ("DEMO-R03-002", 5, 3, "600", 20, "branch"),
        ("DEMO-R03-003", 6, 3, "700", 15, "atm"),
    )
    for number, sender, receiver, amount, minutes_ago, channel in demo_transactions:
        exists = db.scalar(
            select(Transaction.transaction_id).where(
                Transaction.transaction_no == number
            )
        )
        if exists is None:
            db.add(
                Transaction(
                    transaction_no=number,
                    sender_account_id=accounts[sender - 1].account_id,
                    receiver_account_id=accounts[receiver - 1].account_id,
                    amount=Decimal(amount),
                    currency="TRY",
                    tx_time=run_as_of - timedelta(minutes=minutes_ago),
                    channel=channel,
                    country_code="TR",
                )
            )

    db.flush()
    return {
        "customers": 10,
        "accounts": 10,
        "transactions": len(demo_transactions),
        "rules": len(NEW_RULE_WEIGHTS),
        "demo_customer_ids": [customer.customer_id for customer in customers[:3]],
    }
