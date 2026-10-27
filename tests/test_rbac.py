from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.api.dependencies import (
    get_analysis_service,
    get_alert_service,
    get_audit_service,
    get_auth_service,
    get_demo_service,
    get_detection_service,
    get_rule_service,
    get_transaction_service,
    get_upload_service,
    get_user_service,
)
from backend.main import app
from backend.models import Customer
from backend.repositories.alert_repository import SqlAlchemyAlertRepository
from backend.repositories.audit_repository import AuditLogRepository
from backend.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.services.auth_service import AuthService, AuthenticatedUser


ADMIN_PERMISSIONS = frozenset(
    {
        "user:manage",
        "role:manage",
        "upload:create",
        "upload:view",
        "rule:view",
        "rule:edit",
        "customer:view",
        "alert:view",
        "alert:update",
        "dashboard:view",
        "audit:view",
    }
)
ANALYST_PERMISSIONS = frozenset(
    {"alert:view", "alert:update", "dashboard:view"}
)
TEST_SECRET = "test-secret-for-rbac-unit-tests-long"


class MemoryAuditSession:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self._pending: list[Any] = []

    def add(self, record: Any) -> None:
        self._pending.append(record)

    def commit(self) -> None:
        self._rows.extend(self._pending)
        self._pending.clear()

    def rollback(self) -> None:
        self._pending.clear()

    def close(self) -> None:
        pass


class FakeAuthService:
    def login(self, username: str, password: str) -> str | None:
        return "admin" if username == "admin" and password == "correct" else None

    def user_from_token(self, token: str) -> AuthenticatedUser:
        if token == "expired":
            raise jwt.ExpiredSignatureError("Token expired.")
        if token not in {"admin", "analyst"}:
            raise jwt.InvalidTokenError("Invalid token.")
        return AuthenticatedUser(
            user_id=1 if token == "admin" else 2,
            username=token,
            role_code=token,
            permissions=(
                ADMIN_PERMISSIONS if token == "admin" else ANALYST_PERMISSIONS
            ),
        )


class FakeAlertService:
    def __init__(self) -> None:
        self.status_actor_id: int | None = None

    def list_rule_codes(self) -> list[str]:
        return ["R01", "R02"]

    def list_alerts(self, **_kwargs: Any) -> dict[str, Any]:
        return {"total": 1, "items": [{"alert_id": 1, "rule_code": "R01"}]}

    def get_alert(self, _alert_id: int) -> dict[str, Any]:
        return {
            "alert_id": 1,
            "customer": {"customer_no": "C-LINKED", "customer_name": "Linked"},
            "transactions": [{"transaction_id": 14}],
        }

    def customer_transactions_for_alert(self, _alert_id: int, _limit: int):
        return {
            "customer_no": "C-LINKED",
            "customer_name": "Linked",
            "items": [{"transaction_id": 14}],
        }

    def update_status(
        self, alert_id: int, status: str, note: str | None, actor_id: int
    ) -> dict[str, Any]:
        self.status_actor_id = actor_id
        return {"alert_id": alert_id, "status": status, "changed": True}


class FakeRuleService:
    def list_rules(self):
        return [{"rule_code": "R01"}]

    def update_rule(self, rule_code, thresholds, is_active, actor_id, weight=None):
        return {"rule_code": rule_code, "actor_id": actor_id}


class FakeUploadService:
    async def upload(self, entity, _file, actor_id):
        return {"entity_type": entity, "actor_id": actor_id}

    def get_batch(self, batch_id):
        return {"batch_id": batch_id}


class FakeUserService:
    def list_users(self):
        return [{"user_id": 1, "username": "admin"}]

    def list_roles(self):
        return [{"role_code": "admin"}, {"role_code": "analyst"}]

    def create_user(self, **kwargs):
        return {"user_id": 3, "username": kwargs["username"]}

    def update_user(self, user_id, **kwargs):
        return {"user_id": user_id, "is_active": kwargs["is_active"]}


class FakeTransactionService:
    def list_transactions(self, **_kwargs):
        return {"total": 0, "items": []}

    def customer_history(self, customer_no, _limit):
        return {"customer_no": customer_no, "items": []}


class FakeAnalysisService:
    def check_health(self):
        return {"status": "ok"}

    def dashboard_summary(self):
        return {"alerts": 0}


class FakeDetectionService:
    def evaluate(self, **_kwargs):
        return 0


class FakeDemoService:
    def seed(self, _actor_id):
        return {"created_alerts": 0}


class FakeAuditService:
    def list_events(self, _offset, _limit):
        return {"total": 0, "items": []}


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    audit_rows: list[Any] = []
    monkeypatch.setattr(
        "backend.repositories.audit_repository.create_independent_session",
        lambda: MemoryAuditSession(audit_rows),
    )
    alert_service = FakeAlertService()
    app.dependency_overrides.update(
        {
            get_auth_service: FakeAuthService,
            get_analysis_service: FakeAnalysisService,
            get_alert_service: lambda: alert_service,
            get_audit_service: FakeAuditService,
            get_demo_service: FakeDemoService,
            get_detection_service: FakeDetectionService,
            get_rule_service: FakeRuleService,
            get_transaction_service: FakeTransactionService,
            get_upload_service: FakeUploadService,
            get_user_service: FakeUserService,
        }
    )
    with TestClient(app) as client:
        yield client, audit_rows, alert_service
    app.dependency_overrides.clear()


def authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("token", "expected_status"),
    [(None, 401), ("invalid", 401), ("expired", 401)],
)
def test_protected_route_requires_a_valid_token(api_client, token, expected_status):
    client, _audit_rows, _alert_service = api_client
    headers = authorization(token) if token else {}
    assert client.get("/alerts", headers=headers).status_code == expected_status


def test_health_is_public_and_login_uses_oauth_password_form(api_client):
    client, _audit_rows, _alert_service = api_client
    assert client.get("/health").status_code == 200
    success = client.post(
        "/auth/login",
        data={"username": "admin", "password": "correct"},
    )
    failure = client.post(
        "/auth/login",
        data={"username": "admin", "password": "wrong"},
    )
    assert success.status_code == 200
    assert success.json()["token_type"] == "bearer"
    assert failure.status_code == 401
    assert failure.json()["detail"] == "Incorrect username or password."


def test_auth_me_returns_sorted_permissions(api_client):
    client, _audit_rows, _alert_service = api_client
    response = client.get("/auth/me", headers=authorization("admin"))
    assert response.status_code == 200
    assert response.json()["permissions"] == sorted(ADMIN_PERMISSIONS)


@pytest.mark.parametrize(
    ("method", "path", "permission", "kwargs"),
    [
        ("get", "/rules", "rule:view", {}),
        ("put", "/rules/R01", "rule:edit", {"json": {"thresholds": {}, "is_active": True}}),
        ("post", "/rules/evaluate", "rule:edit", {}),
        (
            "post",
            "/uploads?entity=customer",
            "upload:create",
            {"files": {"file": ("customers.csv", b"customer_no\nC-1\n", "text/csv")}},
        ),
        ("get", "/uploads/1", "upload:view", {}),
        ("get", "/transactions", "customer:view", {}),
        ("get", "/customers/C-1/transactions", "customer:view", {}),
        ("get", "/audit-log", "audit:view", {}),
        ("post", "/demo/seed", "upload:create", {}),
        ("get", "/users", "user:manage", {}),
        ("get", "/users/roles", "user:manage", {}),
        (
            "post",
            "/users",
            "user:manage",
            {"json": {"username": "new", "password": "secret", "role_code": "analyst"}},
        ),
        (
            "patch",
            "/users/1",
            "user:manage",
            {"json": {"is_active": False}},
        ),
    ],
)
def test_analyst_is_denied_admin_only_routes_and_audited(
    api_client, method, path, permission, kwargs
):
    client, audit_rows, _alert_service = api_client
    response = getattr(client, method)(path, headers=authorization("analyst"), **kwargs)
    assert response.status_code == 403
    assert any(
        event.action == "ACCESS_DENIED" and event.entity_id == permission
        for event in audit_rows
    )


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "expected_status"),
    [
        ("get", "/rules", {}, 200),
        ("get", "/dashboard/summary", {}, 200),
        ("put", "/rules/R01", {"json": {"thresholds": {}, "is_active": True}}, 200),
        ("post", "/rules/evaluate", {}, 200),
        ("get", "/uploads/1", {}, 200),
        ("get", "/transactions", {}, 200),
        ("get", "/customers/C-1/transactions", {}, 200),
        ("get", "/audit-log", {}, 200),
        ("get", "/users", {}, 200),
        ("get", "/users/roles", {}, 200),
        (
            "post",
            "/users",
            {"json": {"username": "new", "password": "secret", "role_code": "analyst"}},
            201,
        ),
        ("patch", "/users/1", {"json": {"is_active": False}}, 200),
        (
            "post",
            "/uploads?entity=customer",
            {"files": {"file": ("customers.csv", b"customer_no\nC-1\n", "text/csv")}},
            200,
        ),
    ],
)
def test_admin_can_use_admin_routes(
    api_client, method, path, kwargs, expected_status
):
    client, _audit_rows, _alert_service = api_client
    response = getattr(client, method)(path, headers=authorization("admin"), **kwargs)
    assert response.status_code == expected_status


def test_alert_status_actor_comes_from_token_not_request_body(api_client):
    client, _audit_rows, alert_service = api_client
    response = client.patch(
        "/alerts/1/status",
        headers=authorization("analyst"),
        json={"status": "in_review", "note": "Reviewed", "changed_by": 999},
    )
    assert response.status_code == 200
    assert alert_service.status_actor_id == 2


def test_analyst_alert_detail_and_history_are_alert_scoped(api_client):
    client, _audit_rows, _alert_service = api_client
    detail = client.get("/alerts/1", headers=authorization("analyst"))
    history = client.get(
        "/alerts/1/customer-transactions",
        headers=authorization("analyst"),
    )
    assert detail.status_code == 200
    assert detail.json()["customer"]["customer_no"] == "C-LINKED"
    assert detail.json()["transactions"] == [{"transaction_id": 14}]
    assert history.status_code == 200
    assert history.json()["customer_no"] == "C-LINKED"
    assert history.json()["items"] == [{"transaction_id": 14}]


def test_alert_customer_history_query_is_scoped_to_alert_customer():
    customer = Customer(
        customer_id=23,
        customer_no="C-LINKED",
        full_name="Linked customer",
    )
    captured: list[Any] = []

    class EmptyScalars:
        def __iter__(self):
            return iter(())

        def unique(self):
            return self

    class QueryCaptureSession:
        def scalar(self, _statement):
            return SimpleNamespace(customer_id=23, customer=customer)

        def scalars(self, statement):
            captured.append(statement)
            return EmptyScalars()

    result = SqlAlchemyAlertRepository(QueryCaptureSession()).customer_transactions_for_alert(
        10, 200
    )
    assert result == (customer, [])
    compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True}))
    assert "account.customer_id = 23" in compiled
    assert "transaction.sender_account_id IN" in compiled
    assert "transaction.receiver_account_id IN" in compiled


def test_password_hashing_limit_and_jwt_subject(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    password = "correct horse"
    encoded = hash_password(password)
    assert verify_password(password, encoded)
    assert not verify_password("incorrect", encoded)
    with pytest.raises(ValueError, match="72 UTF-8 bytes"):
        hash_password("x" * 73)
    with pytest.raises(ValueError, match="72 UTF-8 bytes"):
        verify_password("x" * 73, encoded)

    token = create_access_token(42)
    assert decode_access_token(token) == 42
    claims = jwt.decode(
        token,
        TEST_SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False},
    )
    assert claims["sub"] == "42"
    remaining = datetime.fromtimestamp(claims["exp"], timezone.utc) - datetime.now(
        timezone.utc
    )
    assert timedelta(minutes=29) <= remaining <= timedelta(minutes=30)


def test_app_startup_requires_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET is required"):
        with TestClient(app):
            pass


@pytest.mark.parametrize(
    ("active_user", "active_role"),
    [(False, True), (True, False)],
)
def test_inactive_user_or_role_invalidates_token(
    api_client, monkeypatch, active_user, active_role
):
    client, _audit_rows, _alert_service = api_client
    user = SimpleNamespace(
        user_id=42,
        username="inactive",
        is_active=active_user,
        role=SimpleNamespace(
            role_code="analyst",
            is_active=active_role,
            permissions=[],
        ),
    )

    class UserRepository:
        def get_by_id(self, _user_id):
            return user

    previous = app.dependency_overrides[get_auth_service]
    app.dependency_overrides[get_auth_service] = lambda: AuthService(
        UserRepository(), AuditLogRepository()
    )
    try:
        response = client.get(
            "/auth/me",
            headers=authorization(create_access_token(42)),
        )
        assert response.status_code == 401
    finally:
        app.dependency_overrides[get_auth_service] = previous


def test_login_audit_events_omit_password(api_client, monkeypatch):
    _client, audit_rows, _alert_service = api_client
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    user = SimpleNamespace(
        user_id=2,
        username="analyst",
        password_hash=hash_password("correct"),
        is_active=True,
        role=SimpleNamespace(
            role_code="analyst",
            is_active=True,
            permissions=[],
        ),
    )

    class UserRepository:
        def get_by_username(self, username):
            return user if username == "analyst" else None

    service = AuthService(UserRepository(), AuditLogRepository())
    assert service.login("analyst", "correct")
    assert service.login("unknown", "do-not-log-this") is None
    assert service.login("analyst", "wrong-password") is None
    actions = [row.action for row in audit_rows]
    assert actions[-3:] == ["LOGIN_SUCCESS", "LOGIN_FAILED", "LOGIN_FAILED"]
    assert all("password" not in str(row.details).lower() for row in audit_rows)
    assert audit_rows[-1].actor_id is None
