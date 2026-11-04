"""PostgreSQL integration tests.

They run against the database in DATABASE_URL, which must be a LOCAL test
database (localhost); anything else (e.g. the Neon production database) makes
them skip. Nothing they write survives: every test runs inside one outer
transaction that is rolled back afterwards. All application sessions (request
sessions and the independent audit session) are bound to that connection with
``join_transaction_mode="create_savepoint"``, so their commits only release
savepoints. Existing rows in the database are left untouched; tests therefore
scope their assertions to the rows they create.

The schema must be at the Alembic head (``alembic upgrade head``).
"""

import os
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
_ENV = dotenv_values(ROOT / ".env")
DB_URL = os.getenv("DATABASE_URL") or _ENV.get("DATABASE_URL")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
JWT_SECRET = "integration-test-secret-that-is-long-enough"


@pytest.fixture(scope="session")
def engine():
    if not DB_URL:
        pytest.skip("DATABASE_URL is not set; integration tests skipped.")
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from backend.db_url import normalize_database_url

    url = normalize_database_url(DB_URL)
    if make_url(url).host not in LOCAL_HOSTS:
        pytest.skip("Integration tests only run against a local test database.")
    engine = create_engine(url)
    head = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head()
    with engine.connect() as connection:
        current = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if current != head:
        pytest.exit(
            f"Database is at {current}, code expects {head}: run `alembic upgrade head`.",
            returncode=2,
        )
    yield engine
    engine.dispose()


@pytest.fixture
def connection(engine) -> Iterator[Any]:
    import backend.database as database

    connection = engine.connect()
    outer = connection.begin()
    previous_factory = database._session_factory
    previous_secret = os.environ.get("JWT_SECRET")
    database._session_factory = sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    os.environ["JWT_SECRET"] = JWT_SECRET
    try:
        yield connection
    finally:
        database._session_factory = previous_factory
        if previous_secret is None:
            os.environ.pop("JWT_SECRET", None)
        else:
            os.environ["JWT_SECRET"] = previous_secret
        outer.rollback()
        connection.close()


@pytest.fixture
def session(connection) -> Iterator[Session]:
    import backend.database as database

    db = database._session_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def users(session) -> dict[str, dict[str, Any]]:
    """Fresh users per test (rolled back with everything else)."""
    from backend.security import create_access_token

    suffix = uuid4().hex[:8]
    result: dict[str, dict[str, Any]] = {}
    for key in ("analyst", "analyst2", "compliance", "compliance2", "admin"):
        role = "".join(ch for ch in key if not ch.isdigit())
        username = f"it-{key}-{suffix}"
        user_id = session.execute(
            text(
                "INSERT INTO app_user (username, password_hash, role_id) "
                "SELECT :username, 'not-a-login-hash', role_id FROM app_role "
                "WHERE role_code = :role RETURNING user_id"
            ),
            {"username": username, "role": role},
        ).scalar_one()
        result[key] = {
            "user_id": user_id,
            "username": username,
            "role": role,
            "headers": {"Authorization": f"Bearer {create_access_token(user_id)}"},
        }
    session.commit()
    return result


@pytest.fixture
def client(connection, users):
    """API client whose request sessions share the test transaction.

    In production the independent audit session (ACCESS_DENIED, etc.) uses its own
    connection. Here it shares one connection, so its savepoint is nested inside the
    request session's savepoint; rolling the request savepoint back on close would
    also discard the audit row. Request sessions therefore release (commit) their
    savepoint on close. Every error path in the application rolls back explicitly
    before that, so this does not hide partial writes.
    """
    from fastapi.testclient import TestClient

    import backend.database as database
    from backend.database import get_db
    from backend.main import app

    def test_get_db():
        db = database._session_factory()
        try:
            yield db
        finally:
            try:
                if db.in_transaction():
                    db.commit()
            except Exception:
                db.rollback()
            db.close()

    app.dependency_overrides[get_db] = test_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


class Factory:
    """Small helpers that insert rows directly with SQL."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._seq = 0

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def customer(
        self,
        name: str = "Ahmet Yılmaz",
        *,
        customer_no: str | None = None,
        customer_type: str = "BIREYSEL",
        occupation: str | None = "Öğretmen",
        monthly_income: str | None = "28000.00",
        risk_level: str | None = "medium",
        created_at: datetime | None = None,
    ):
        from backend.models import Customer

        customer = Customer(
            customer_no=customer_no or f"IT-{uuid4().hex[:8]}-{self._next()}",
            full_name=name,
            customer_type=customer_type,
            occupation=occupation,
            monthly_income=Decimal(monthly_income) if monthly_income else None,
            risk_level=risk_level,
        )
        if created_at:
            customer.created_at = created_at
        self.session.add(customer)
        self.session.flush()
        return customer

    def account(self, customer, *, account_no: str | None = None, currency: str = "TRY"):
        from backend.models import Account

        account = Account(
            account_no=account_no or f"TRIT{uuid4().hex[:12]}{self._next():06d}",
            customer_id=customer.customer_id,
            currency=currency,
            account_type="current",
        )
        self.session.add(account)
        self.session.flush()
        return account

    def transaction(
        self,
        sender,
        receiver,
        amount: str = "1000.00",
        *,
        tx_time: datetime | None = None,
        currency: str = "TRY",
        channel: str = "internet",
        country_code: str = "TR",
    ):
        from backend.models import Transaction

        tx = Transaction(
            transaction_no=f"IT-{uuid4().hex[:12]}-{self._next()}",
            sender_account_id=sender.account_id,
            receiver_account_id=receiver.account_id,
            amount=Decimal(amount),
            currency=currency,
            tx_time=tx_time or datetime.now(),
            channel=channel,
            country_code=country_code,
        )
        self.session.add(tx)
        self.session.flush()
        return tx

    def rule_id(self, code: str) -> int:
        from backend.models import MonitoringRule

        return self.session.scalar(
            select(MonitoringRule.rule_id).where(MonitoringRule.rule_code == code)
        )

    def alert(
        self,
        customer,
        rule_code: str = "R05",
        *,
        status: str = "new",
        score: str = "0.8000",
        severity: str | None = None,
        created_at: datetime | None = None,
        transactions: list | None = None,
    ):
        from backend.detection.evidence import alert_severity
        from backend.models import Alert, AlertTransaction

        alert = Alert(
            rule_id=self.rule_id(rule_code),
            customer_id=customer.customer_id,
            severity=severity or alert_severity(Decimal(score)),
            score=Decimal(score),
            status=status,
            deduplication_key=f"it:{rule_code}:{customer.customer_id}:{uuid4().hex}",
        )
        if created_at:
            alert.created_at = created_at
        self.session.add(alert)
        self.session.flush()
        for tx in transactions or []:
            self.session.add(
                AlertTransaction(alert_id=alert.alert_id, transaction_id=tx.transaction_id)
            )
        self.session.flush()
        return alert

    def history(self, alert, user_id: int, old: str | None, new: str, note: str = "not", at=None):
        from backend.models import AlertStatusHistory

        row = AlertStatusHistory(
            alert_id=alert.alert_id,
            changed_by=user_id,
            old_status=old,
            new_status=new,
            note=note,
        )
        if at:
            row.changed_at = at
        self.session.add(row)
        self.session.flush()
        return row

    def commit(self) -> None:
        self.session.commit()


@pytest.fixture
def factory(session) -> Factory:
    return Factory(session)
