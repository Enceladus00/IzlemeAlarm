"""Insert example customers, accounts and transactions shaped like the demo lab data.

Each batch reuses the demo lab's 32-customer scenario layout
(backend.demo._scenario_transactions) so every rule has data that exercises it,
but with random names, customer numbers, IBAN-style account numbers and
transaction numbers. Only inserts rows: DEMO-* data and everything else is left
untouched. Writes to the database in DATABASE_URL.

Run:  python -m backend.scripts.seed_example_data [--batches N] [--seed S]
"""

import argparse
import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from backend.database import create_independent_session
from backend.demo import DEMO_CUSTOMER_COUNT, _scenario_transactions
from backend.models import Account, Customer, Transaction

FIRST_NAMES = (
    "Ahmet", "Mehmet", "Ayşe", "Fatma", "Mustafa", "Zeynep", "Emre", "Elif",
    "Hüseyin", "Merve", "Burak", "Selin", "Can", "Deniz", "Ece", "Kerem",
    "Gizem", "Oğuz", "Sevgi", "Murat", "Derya", "Serkan", "Pınar", "Tolga",
)
LAST_NAMES = (
    "Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Aydın", "Öztürk",
    "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt",
)
OCCUPATIONS = ("Öğretmen", "Mühendis", "Hemşire", "Muhasebeci", "Doktor", "Avukat")
COMPANY_PLACES = (
    "Anadolu", "Ege", "Marmara", "Karadeniz", "Akdeniz", "Trakya", "Başkent",
    "Kapadokya", "Boğaziçi", "Toros", "Uludağ", "Fırat", "Dicle", "Kızılırmak",
)
COMPANY_SECTORS = (
    ("Gıda", "Gıda toptan"), ("Lojistik", "Lojistik"), ("Yazılım", "Yazılım"),
    ("İnşaat", "İnşaat"), ("Turizm", "Turizm"), ("Tekstil", "Tekstil"),
    ("Danışmanlık", "Danışmanlık"), ("Otomotiv", "Otomotiv"), ("Enerji", "Enerji"),
    ("Kimya", "Kimya"), ("Mobilya", "Mobilya"), ("Elektronik", "Elektronik"),
)
COMPANY_SUFFIXES = ("A.Ş.", "Ltd. Şti.")
# Scenario slots (1-32, see backend.demo._scenario_transactions) played by a
# company: fan-in collector, fan-out distributor, the R05/R06 counterparties,
# the R09 depositor, the hub, the foreign counterparty and one hub partner.
# Everyone else is an individual.
CORPORATE_SLOTS = {11, 12, 19, 20, 23, 27, 28, 29}
# Slots whose scenario looks like money laundering get a high risk rating:
# layering chain end, the confirmed-suspicious contact, listed-country and
# round-amount senders, the fan-in collector.
HIGH_RISK_SLOTS = {11, 16, 22, 25, 26}
MEDIUM_RISK_SLOTS = {1, 3, 7, 10, 13, 17, 24}


def _unique(rng: random.Random, used: set[str], make) -> str:
    while True:
        value = make()
        if value not in used:
            used.add(value)
            return value


def _apply_profile(rng: random.Random, used_names: set[str], customer: Customer, slot: int) -> None:
    """Name, type, occupation, income and risk for the customer in scenario `slot`."""
    if slot in CORPORATE_SLOTS:
        sector, occupation = rng.choice(COMPANY_SECTORS)
        customer.full_name = _unique(
            rng, used_names, lambda: f"{rng.choice(COMPANY_PLACES)} {sector} {rng.choice(COMPANY_SUFFIXES)}"
        )
        customer.customer_type = "KURUMSAL"
    else:
        customer.full_name = _unique(
            rng, used_names, lambda: f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        )
        customer.customer_type = "BIREYSEL"
        occupation = rng.choice(OCCUPATIONS)
    customer.occupation = occupation
    # Same income as the demo lab so the income-based rules (R01, R04, R05) behave alike.
    customer.monthly_income = Decimal("50000.00")
    customer.risk_level = (
        "high" if slot in HIGH_RISK_SLOTS else "medium" if slot in MEDIUM_RISK_SLOTS else "low"
    )


def relabel(seed_value: int | None) -> int:
    """Apply the current type/name/risk layout to MUS-* customers already in the DB."""
    rng = random.Random(seed_value)
    with create_independent_session() as session:
        customers = list(
            session.scalars(
                select(Customer).where(Customer.customer_no.like("MUS-%")).order_by(Customer.customer_no)
            )
        )
        used_names = set(session.scalars(select(Customer.full_name))) - {c.full_name for c in customers}
        for position, customer in enumerate(customers):
            _apply_profile(rng, used_names, customer, position % DEMO_CUSTOMER_COUNT + 1)
        session.commit()
    return len(customers)


def _new_customer(session, rng, used_names, next_no: list[int], *, corporate=False, income="50000",
                  occupation=None, risk="low", opened_days=900) -> tuple[Customer, Account]:
    customer = Customer(customer_no=f"MUS-{next_no[0]}", is_active=True)
    next_no[0] += 1
    if corporate:
        sector, sector_name = rng.choice(COMPANY_SECTORS)
        customer.full_name = _unique(
            rng, used_names, lambda: f"{rng.choice(COMPANY_PLACES)} {sector} {rng.choice(COMPANY_SUFFIXES)}"
        )
        customer.customer_type, customer.occupation = "KURUMSAL", sector_name
    else:
        customer.full_name = _unique(rng, used_names, lambda: f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}")
        customer.customer_type, customer.occupation = "BIREYSEL", occupation or rng.choice(OCCUPATIONS)
    customer.monthly_income = Decimal(income)
    customer.risk_level = risk
    session.add(customer)
    session.flush()
    account = Account(
        account_no=f"TR{rng.randint(10, 99)}000610{rng.randint(0, 10**16 - 1):016d}",
        customer_id=customer.customer_id,
        currency="TRY",
        account_type="current",
        opened_at=datetime.now().date() - timedelta(days=opened_days),
        is_active=True,
    )
    session.add(account)
    session.flush()
    return customer, account


def extras(background: int, seed_value: int | None) -> dict[str, int]:
    """Scenarios the demo layout cannot trigger with the production parameters
    (R01, R07, R10, R15) plus `background` everyday customers with ~90 days of
    salaries, rent, shopping and cash withdrawals."""
    from sqlalchemy import text

    from backend.models import Alert, AlertStatusHistory, AppUser, MonitoringRule

    rng = random.Random(seed_value)
    now = datetime.now().replace(microsecond=0)
    counts = {"customers": 0, "transactions": 0, "alerts": 0}
    with create_independent_session() as session:
        used_names = set(session.scalars(select(Customer.full_name)))
        last = session.scalar(
            select(func.max(Customer.customer_no)).where(Customer.customer_no.like("MUS-%"))
        )
        next_no = [int(last.removeprefix("MUS-")) + 1 if last else 100001]
        tx_counter = [0]
        stamp = now.strftime("%y%m%d%H%M")

        def tx(sender: Account, receiver: Account, amount, at: datetime, channel="mobile", country="TR"):
            if at >= now:
                return
            tx_counter[0] += 1
            session.add(
                Transaction(
                    transaction_no=f"EX-{stamp}-{tx_counter[0]:06d}",
                    sender_account_id=sender.account_id,
                    receiver_account_id=receiver.account_id,
                    amount=Decimal(str(amount)).quantize(Decimal("0.01")),
                    currency="TRY",
                    tx_time=at,
                    channel=channel,
                    country_code=country,
                    is_active=True,
                )
            )

        def person(**kwargs):
            counts["customers"] += 1
            return _new_customer(session, rng, used_names, next_no, **kwargs)

        cash_desk_customer, cash_desk = person(corporate=True, income="0", risk="low", opened_days=3000)
        cash_desk_customer.full_name = "İzleme Bank Kasa Hesabı"
        cash_desk_customer.occupation = "Banka iç hesap"
        merchants = [person(corporate=True, income=str(rng.randint(8, 40) * 100000))[1] for _ in range(6)]

        # R01: a student whose many just-under-limit transfers add up to over half the monthly income.
        _, student = person(income="4500", occupation="Öğrenci", risk="medium")
        friends = [person(income=str(rng.randint(25, 60) * 1000))[1] for _ in range(3)]
        for hours, amount in enumerate((465, 480, 490, 470, 495, 485), 1):
            tx(student, rng.choice(friends), amount, now - timedelta(days=hours // 2, hours=hours * 3))

        # R07: an account untouched for ~7 months suddenly moves 30,000 TRY this week.
        _, sleeper = person(income="30000", risk="medium", opened_days=1500)
        tx(rng.choice(merchants), sleeper, 1200, now - timedelta(days=215))
        tx(rng.choice(merchants), sleeper, 30000, now - timedelta(days=2, hours=4))
        tx(sleeper, cash_desk, 28000, now - timedelta(days=1, hours=6), "atm")

        # R10: 25,000 TRY arrives and 96% leaves for a never-seen recipient within hours.
        _, passer = person(income="35000", risk="high")
        _, newcomer_recipient = person(income="20000")
        tx(rng.choice(merchants), passer, 25000, now - timedelta(hours=10), "internet")
        tx(passer, newcomer_recipient, 24000, now - timedelta(hours=3), "internet")

        # R15: a customer an analyst confirmed as suspicious, and two people who traded with them.
        suspect_customer, suspect = person(income="40000", risk="high")
        _, direct_contact = person(income="45000", risk="medium")
        _, indirect_contact = person(income="38000")
        tx(direct_contact, suspect, 7500, now - timedelta(days=3))
        tx(indirect_contact, direct_contact, 5000, now - timedelta(days=2))
        analyst_id = session.scalar(select(AppUser.user_id).order_by(AppUser.user_id).limit(1))
        rule_id = session.scalar(select(MonitoringRule.rule_id).where(MonitoringRule.rule_code == "R16"))
        if analyst_id and rule_id:
            alert = Alert(
                rule_id=rule_id,
                customer_id=suspect_customer.customer_id,
                severity="high",
                score=Decimal("1"),
                status="confirmed_suspicious",
                deduplication_key=f"example:R16:{suspect_customer.customer_no}",
                created_at=now - timedelta(days=20),
            )
            session.add(alert)
            session.flush()
            for old, new, days, note in (
                (None, "new", 20, None),
                ("new", "in_review", 18, "Yüksek riskli ülkeye tekrarlayan transferler, uyum birimine iletildi."),
                ("in_review", "confirmed_suspicious", 15, "Belgeler yetersiz; şüpheli işlem bildirimi yapıldı."),
            ):
                session.add(
                    AlertStatusHistory(
                        alert_id=alert.alert_id,
                        changed_by=analyst_id,
                        old_status=old,
                        new_status=new,
                        note=note,
                        changed_at=now - timedelta(days=days),
                    )
                )
            counts["alerts"] += 1

        # Everyday background customers.
        people = [
            person(
                income=str(rng.choice((18, 25, 32, 38, 45, 60, 80, 110)) * 1000),
                risk=rng.choices(("low", "medium", "high"), (80, 17, 3))[0],
                opened_days=rng.randint(200, 3000),
            )
            for _ in range(background)
        ]
        employers = merchants[:3]
        day = now.date() - timedelta(days=90)
        while day <= now.date():
            for customer, account in people:
                def at(low=8, high=21):
                    return datetime.combine(day, datetime.min.time()) + timedelta(
                        hours=rng.randint(low, high), minutes=rng.randint(0, 59)
                    )
                if day.day == 1:
                    tx(rng.choice(employers), account, customer.monthly_income, at(9, 11), "internet")
                if day.day == 5:
                    landlord = rng.choice(people)[1]
                    tx(account, landlord, int(customer.monthly_income * Decimal("0.3")) // 100 * 100, at())
                if rng.random() < 0.12:
                    tx(account, rng.choice(merchants), round(rng.uniform(60, 1800), 2), at(), rng.choice(("mobile", "internet")))
                if rng.random() < 0.03:
                    tx(account, cash_desk, rng.choice((500, 1000, 2000)), at(), "atm")
                if rng.random() < 0.02:
                    tx(account, rng.choice(people)[1], rng.choice((150, 300, 500, 1000)), at())
            day += timedelta(days=1)
        counts["transactions"] = tx_counter[0]
        session.commit()
    return counts


def seed(batches: int, seed_value: int | None) -> dict[str, int]:
    rng = random.Random(seed_value)
    as_of = datetime.now()
    created = {"customers": 0, "accounts": 0, "transactions": 0}
    with create_independent_session() as session:
        used_names = set(session.scalars(select(Customer.full_name)))
        next_customer = 100001 + int(
            session.scalar(
                select(func.count()).select_from(Customer).where(Customer.customer_no.like("MUS-%"))
            )
            or 0
        )
        used_accounts = set(session.scalars(select(Account.account_no)))
        used_tx = set(session.scalars(select(Transaction.transaction_no).where(Transaction.transaction_no.like("EX-%"))))
        for _ in range(batches):
            customers: list[Customer] = []
            for index in range(1, DEMO_CUSTOMER_COUNT + 1):
                customer = Customer(customer_no=f"MUS-{next_customer}", is_active=True)
                _apply_profile(rng, used_names, customer, index)
                next_customer += 1
                session.add(customer)
                customers.append(customer)
            session.flush()

            accounts: list[Account] = []
            for index, customer in enumerate(customers, 1):
                account_no = _unique(
                    rng, used_accounts, lambda: f"TR{rng.randint(10, 99)}000610{rng.randint(0, 10**16 - 1):016d}"
                )
                account = Account(
                    account_no=account_no,
                    customer_id=customer.customer_id,
                    currency="TRY",
                    account_type="current",
                    # Customer 8 has a brand-new account (R08), as in the demo lab.
                    opened_at=as_of.date() - timedelta(days=14 if index == 8 else rng.randint(365, 2500)),
                    is_active=True,
                )
                session.add(account)
                accounts.append(account)
            session.flush()

            for number, sender, receiver, amount, tx_time, channel, country in _scenario_transactions(as_of):
                transaction_no = _unique(
                    rng, used_tx, lambda: f"EX-{number.removeprefix('D-')}-{rng.randint(0, 10**6 - 1):06d}"
                )
                session.add(
                    Transaction(
                        transaction_no=transaction_no,
                        sender_account_id=accounts[sender - 1].account_id,
                        receiver_account_id=accounts[receiver - 1].account_id,
                        amount=Decimal(amount),
                        currency="TRY",
                        tx_time=tx_time,
                        channel=channel,
                        country_code=country,
                        is_active=True,
                    )
                )
                created["transactions"] += 1
            created["customers"] += len(customers)
            created["accounts"] += len(accounts)
        session.commit()
    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batches", type=int, default=1, help="number of 32-customer batches")
    parser.add_argument("--seed", type=int, default=None, help="random seed (default: random)")
    parser.add_argument(
        "--relabel", action="store_true", help="only re-apply names/types/risk to existing MUS-* customers"
    )
    parser.add_argument(
        "--extras", action="store_true", help="add the R01/R07/R10/R15 scenarios and background customers"
    )
    parser.add_argument("--background", type=int, default=40, help="everyday customers added with --extras")
    args = parser.parse_args()
    if args.relabel:
        print({"relabelled": relabel(args.seed)})
    else:
        if args.batches:
            print(seed(args.batches, args.seed))
        if args.extras:
            print(extras(args.background, args.seed))
