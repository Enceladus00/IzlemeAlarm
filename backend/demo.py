from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.detection.parameters import validate_rule_parameters
from backend.detection.registry import load_rule_registry
from backend.models import Account, Customer, MonitoringRule, Transaction


NEW_RULE_WEIGHTS = {
    "R01": Decimal("1.000"),
    "R02": Decimal("0.450"),
    **{f"R{number:02d}": Decimal("1.000") for number in range(3, 16)},
}
UNSET_THRESHOLDS = {
    "BIREYSEL": {"status": "UNSET", "values": {}},
    "KURUMSAL": {"status": "UNSET", "values": {}},
}


def _demo_parameter_set(values: dict[str, Any]) -> dict[str, Any]:
    return {
        customer_type: {"status": "PROVISIONAL", "values": values}
        for customer_type in ("BIREYSEL", "KURUMSAL")
    }


DEMO_RULE_OVERRIDES = {
    "R01": _demo_parameter_set(
        {
            "limits": {"TRY": "10000"},
            "x_esik": 1,
            "x_kesin": 3,
            "minimum_income_ratio": "0.01",
            "income_currency": "TRY",
            "window_days": 7,
        }
    ),
    "R02": _demo_parameter_set({"limits": {"TRY": "15000"}}),
    "R03": _demo_parameter_set(
        {
            "limits": {"TRY": "1000"},
            "x_esik": 1,
            "x_kesin": 3,
            "cash_channels": ["atm", "branch"],
            "window_days": 7,
        }
    ),
    "R04": _demo_parameter_set(
        {"x_esik": "0.5", "x_kesin": "1.5", "window_days": 14}
    ),
    "R05": _demo_parameter_set(
        {
            "x_esik": 1,
            "x_kesin": 3,
            "history_days": 90,
            "kappa": "1",
            "mad_floor": "0.1",
            "income_bands": 2,
        }
    ),
    "R06": _demo_parameter_set(
        {
            "x_esik": 1,
            "x_kesin": 3,
            "history_weeks": 4,
            "min_count": 3,
            "season_factor": {},
        }
    ),
    "R07": _demo_parameter_set(
        {
            "x_esik": 0,
            "x_kesin": 2,
            "dormant_days": 30,
            "window_days": 7,
            "limits": {"TRY": "10000"},
        }
    ),
    "R08": _demo_parameter_set(
        {
            "x_esik": 0,
            "x_kesin": 2,
            "account_age_days": 30,
            "limits": {"TRY": "10000"},
        }
    ),
    "R09": _demo_parameter_set(
        {
            "x_esik": "0.2",
            "x_kesin": "0.6",
            "window_days": 7,
            "baseline_days": 7,
            "cash_channels": ["atm", "branch"],
            "limits": {"TRY": "1000"},
        }
    ),
    "R10": _demo_parameter_set(
        {
            "x_esik": "0.25",
            "x_kesin": "0.75",
            "window_hours": 24,
            "limits": {"TRY": "1000"},
            "ratio_low": "0.5",
            "ratio_high": "1.2",
            "cash_accounts": [],
        }
    ),
    "R11": _demo_parameter_set(
        {
            "x_esik": 3,
            "x_kesin": 6,
            "window_days": 7,
            "cash_accounts": [],
        }
    ),
    "R12": _demo_parameter_set(
        {
            "x_esik": 3,
            "x_kesin": 6,
            "window_days": 7,
            "cash_accounts": [],
            "cv_threshold": "0.1",
            "cv_multiplier": "1.5",
        }
    ),
    "R13": _demo_parameter_set(
        {
            "x_esik": 2,
            "x_kesin": 4,
            "window_days": 7,
            "max_step_hours": 24,
            "decay_low": "0.6",
            "decay_high": "0.95",
            "max_depth": 4,
            "cash_accounts": [],
        }
    ),
    "R14": _demo_parameter_set(
        {
            "x_esik": 1,
            "x_kesin": 3,
            "window_days": 7,
            "max_cycle_length": 4,
            "min_retained": "0.5",
            "pingpong_tolerance": "0.1",
            "cash_accounts": [],
        }
    ),
    "R15": _demo_parameter_set(
        {
            "window_days": 7,
            "suspicious_status": "confirmed_suspicious",
            "gamma": "0.75",
            "cash_accounts": [],
        }
    ),
}


DEMO_SCENARIOS = (
    (
        "R01",
        "DEMO-001",
        "DEMO-ACC-001",
        "Repeated transfers just below the configured limit.",
    ),
    (
        "R02",
        "DEMO-002",
        "DEMO-ACC-002",
        "One outgoing transfer above the configured limit.",
    ),
    (
        "R03",
        "DEMO-003",
        "DEMO-ACC-003",
        "Three below-limit cash deposits into one account.",
    ),
    (
        "R04",
        "DEMO-004",
        "DEMO-ACC-004",
        "Recent external volume above monthly income.",
    ),
    (
        "R05",
        "DEMO-005",
        "DEMO-ACC-005",
        "One unusually large transfer against prior and peer history.",
    ),
    (
        "R06",
        "DEMO-006",
        "DEMO-ACC-006",
        "Current-week activity spike after four quiet baseline weeks.",
    ),
    (
        "R07",
        "DEMO-007",
        "DEMO-ACC-007",
        "Activity resumes after a 30-day dormant gap.",
    ),
    (
        "R08",
        "DEMO-008",
        "DEMO-ACC-008",
        "High transfer volume on a recently opened account.",
    ),
    (
        "R09",
        "DEMO-009",
        "DEMO-ACC-009",
        "Cash share rises against the immediately preceding period.",
    ),
    (
        "R10",
        "DEMO-010",
        "DEMO-ACC-010",
        "Incoming funds are quickly passed to a new recipient.",
    ),
    (
        "R11",
        "DEMO-011",
        "DEMO-ACC-011",
        "Funds arrive from several newly encountered senders.",
    ),
    (
        "R12",
        "DEMO-012",
        "DEMO-ACC-012",
        "Similar-sized transfers go to several new recipients.",
    ),
    (
        "R13",
        "DEMO-014",
        "DEMO-ACC-014",
        "Customer participates in a decreasing three-hop transfer chain.",
    ),
    (
        "R14",
        "DEMO-018",
        "DEMO-ACC-018",
        "Customer participates in a closed three-transfer cycle.",
    ),
    (
        "R15",
        "DEMO-024",
        "DEMO-ACC-024",
        "Two-hop contact with the synthetic confirmed-suspicious customer.",
    ),
)


def _scenario_transactions(
    as_of: datetime,
) -> list[tuple[str, int, int, str, datetime, str]]:
    specs: list[tuple[str, int, int, str, datetime, str]] = []

    def add(
        transaction_no: str,
        sender: int,
        receiver: int,
        amount: str,
        at: datetime,
        channel: str = "internet",
    ) -> None:
        specs.append((transaction_no, sender, receiver, amount, at, channel))

    def recent(days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
        return as_of - timedelta(days=days, hours=hours, minutes=minutes)

    for suffix, amount, minutes in (
        ("001", "9500", 70),
        ("002", "9700", 40),
        ("003", "9800", 15),
    ):
        add(f"D-R01-{suffix}", 1, 13 + int(suffix[-1]), amount, recent(minutes=minutes))
    add("D-R02-001", 2, 13, "16000", recent(minutes=30), "mobile")
    for suffix, sender, amount, channel, minutes in (
        ("001", 14, "500", "atm", 25),
        ("002", 15, "600", "branch", 20),
        ("003", 16, "700", "atm", 15),
    ):
        add(f"D-R03-{suffix}", sender, 3, amount, recent(minutes=minutes), channel)

    add("D-R04-001", 17, 4, "60000", recent(days=4))
    add("D-R04-002", 18, 4, "60000", recent(days=2))

    for customer_index in (4, 5, 8, 9, 10, 11, 12):
        for history_index, amount in enumerate(("300", "350", "400", "450"), 1):
            add(
                f"D-R05-H{customer_index:02d}-{history_index}",
                19,
                customer_index,
                amount,
                recent(days=15 * history_index + customer_index),
            )
    add("D-R05-001", 19, 5, "50000", recent(hours=1))

    week_start = datetime.combine(
        as_of.date() - timedelta(days=as_of.date().weekday()), time.min
    )
    for week_index in range(1, 5):
        add(
            f"D-R06-H{week_index:02d}",
            20,
            6,
            "100",
            week_start - timedelta(days=7 * week_index) + timedelta(days=2, hours=9),
        )
    for suffix, hours in enumerate((5, 4, 3, 2), 1):
        add(f"D-R06-{suffix:03d}", 6, 20, "200", recent(hours=hours))

    add("D-R07-H01", 21, 7, "100", recent(days=45))
    for suffix, days in enumerate((3, 2, 1), 1):
        add(f"D-R07-{suffix:03d}", 7, 21, "10000", recent(days=days))
    add("D-R08-001", 22, 8, "15000", recent(days=9))
    add("D-R08-002", 8, 22, "15000", recent(days=3))

    add("D-R09-B01", 23, 9, "1000", recent(days=10), "atm")
    add("D-R09-B02", 23, 9, "9000", recent(days=10))
    add("D-R09-C01", 23, 9, "9000", recent(days=2), "atm")
    add("D-R09-C02", 23, 9, "1000", recent(days=2))

    add("D-R10-001", 13, 10, "5000", recent(hours=12))
    add("D-R10-002", 10, 14, "4500", recent(hours=6))

    for suffix, sender in enumerate((1, 2, 3, 4, 5, 6), 1):
        add(f"D-R11-{suffix:03d}", sender, 11, "1200", recent(days=1, minutes=suffix))
    for suffix, receiver in enumerate((1, 2, 3, 4, 5, 6), 1):
        add(f"D-R12-{suffix:03d}", 12, receiver, "2000", recent(days=1, minutes=suffix))

    for suffix, sender, receiver, amount, days in (
        ("001", 13, 14, "12000", 4),
        ("002", 14, 15, "9000", 3),
        ("003", 15, 16, "6750", 2),
    ):
        add(f"D-R13-{suffix}", sender, receiver, amount, recent(days=days))

    for suffix, sender, receiver, amount, days in (
        ("001", 17, 18, "8000", 3),
        ("002", 18, 19, "7000", 2),
        ("003", 19, 17, "6000", 1),
        ("004", 20, 21, "5000", 2),
        ("005", 21, 20, "4900", 1),
    ):
        add(f"D-R14-{suffix}", sender, receiver, amount, recent(days=days))

    add("D-R15-001", 24, 23, "2000", recent(days=2))
    add("D-R15-002", 23, 22, "2000", recent(days=1))
    return specs


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

    customer_numbers = [f"DEMO-{index:03d}" for index in range(1, 25)]
    customers_by_number = {
        customer.customer_no: customer
        for customer in db.scalars(
            select(Customer).where(Customer.customer_no.in_(customer_numbers))
        )
    }
    customers: list[Customer] = []
    for index, customer_no in enumerate(customer_numbers, 1):
        customer = customers_by_number.get(customer_no)
        customer_type = "BIREYSEL" if index <= 3 else "KURUMSAL"
        if customer is None:
            customer = Customer(
                customer_no=customer_no,
                customer_type=customer_type,
                occupation="Synthetic demo scenario",
                monthly_income=Decimal("50000.00"),
                risk_level="low",
            )
            db.add(customer)
        customer.full_name = f"Demo Customer {index:02d}"
        customer.customer_type = customer_type
        customer.occupation = "Synthetic demo scenario"
        customer.monthly_income = Decimal("50000.00")
        customer.risk_level = "low"
        customer.is_active = True
        customers.append(customer)
    db.flush()

    account_numbers = [f"DEMO-ACC-{index:03d}" for index in range(1, 25)]
    accounts_by_number = {
        account.account_no: account
        for account in db.scalars(
            select(Account).where(Account.account_no.in_(account_numbers))
        )
    }
    accounts: list[Account] = []
    for index, (customer, account_no) in enumerate(
        zip(customers, account_numbers, strict=True), 1
    ):
        account = accounts_by_number.get(account_no)
        if account is None:
            account = Account(
                account_no=account_no,
                customer_id=customer.customer_id,
                currency="TRY",
                account_type="current",
                opened_at=run_as_of.date() - timedelta(days=365),
            )
            db.add(account)
        account.customer_id = customer.customer_id
        account.currency = "TRY"
        account.account_type = "current"
        account.opened_at = (
            run_as_of.date() - timedelta(days=14)
            if index == 8
            else run_as_of.date() - timedelta(days=365)
        )
        account.is_active = True
        accounts.append(account)
    db.flush()

    transaction_specs = _scenario_transactions(run_as_of)
    transaction_numbers = [spec[0] for spec in transaction_specs]
    legacy_transactions = db.scalars(
        select(Transaction).where(
            Transaction.transaction_no.in_(
                [
                    "DEMO-R01-001",
                    "DEMO-R01-002",
                    "DEMO-R02-001",
                    "DEMO-R03-001",
                    "DEMO-R03-002",
                    "DEMO-R03-003",
                ]
            )
        )
    )
    for transaction in legacy_transactions:
        transaction.is_active = False
    transactions_by_number = {
        transaction.transaction_no: transaction
        for transaction in db.scalars(
            select(Transaction).where(
                Transaction.transaction_no.in_(transaction_numbers)
            )
        )
    }
    for number, sender, receiver, amount, tx_time, channel in transaction_specs:
        transaction = transactions_by_number.get(number)
        if transaction is None:
            transaction = Transaction(transaction_no=number)
            db.add(transaction)
        transaction.sender_account_id = accounts[sender - 1].account_id
        transaction.receiver_account_id = accounts[receiver - 1].account_id
        transaction.amount = Decimal(amount)
        transaction.currency = "TRY"
        transaction.tx_time = tx_time
        transaction.channel = channel
        transaction.country_code = "TR"
        transaction.is_active = True

    db.flush()
    customers_by_number = {customer.customer_no: customer for customer in customers}
    scenario_targets = [
        {
            "rule_code": rule_code,
            "customer_no": customer_no,
            "account_no": account_no,
            "customer_id": customers_by_number[customer_no].customer_id,
            "intent": intent,
            "expected_signal": "score >= 0.50",
        }
        for rule_code, customer_no, account_no, intent in DEMO_SCENARIOS
    ]
    return {
        "customers": len(customers),
        "accounts": len(accounts),
        "transactions": len(transaction_specs),
        "rules": len(NEW_RULE_WEIGHTS),
        "demo_customer_ids": [customer.customer_id for customer in customers],
        "demo_suspicious_customer_ids": [customers[21].customer_id],
        "scenarios": scenario_targets,
    }
