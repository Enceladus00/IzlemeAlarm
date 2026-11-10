from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.api.dependencies import get_auth_service, get_detection_service
from backend.main import create_app
from backend.rate_limit import (
    ANONYMOUS_ADDRESS_RATE,
    GENERAL_RATE,
    LOGIN_ADDRESS_LIMIT,
    LOGIN_PAIR_LIMIT,
    MAX_CONCURRENT_PASSWORD_CHECKS,
    RULE_EVALUATION_RATE,
    SlidingWindowLimiter,
    client_address,
    password_checks,
)
from backend.request_guards import MAX_BODY_BYTES, MAX_UPLOAD_BODY_BYTES
from backend.security import create_access_token
from backend.services.auth_service import AuthenticatedUser


class Clock:
    now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_blocks_at_the_limit_until_the_window_passes():
    clock = Clock()
    limiter = SlidingWindowLimiter(clock=clock)
    assert all(limiter.acquire("k", 2, 60).allowed for _ in range(2))
    blocked = limiter.acquire("k", 2, 60)
    assert not blocked.allowed and blocked.retry_after == 60
    clock.now += 60
    assert limiter.acquire("k", 2, 60).allowed


def test_only_the_first_rejection_of_a_block_is_flagged():
    clock = Clock()
    limiter = SlidingWindowLimiter(clock=clock)
    limiter.acquire("k", 1, 60)
    assert limiter.acquire("k", 1, 60).first_rejection
    assert not limiter.acquire("k", 1, 60).first_rejection
    clock.now += 61
    limiter.acquire("k", 1, 60)
    assert limiter.acquire("k", 1, 60).first_rejection


def test_release_gives_back_one_hit_and_clear_forgets_the_key():
    limiter = SlidingWindowLimiter(clock=Clock())
    limiter.acquire("k", 1, 60)
    limiter.release("k")
    assert limiter.acquire("k", 1, 60).allowed
    limiter.clear("k")
    assert limiter.acquire("k", 1, 60).allowed


def test_tracked_keys_stay_bounded():
    clock = Clock()
    limiter = SlidingWindowLimiter(max_keys=10, clock=clock)
    for index in range(100):
        limiter.acquire(f"k{index}", 1, 60)
    assert len(limiter._buckets) == 10
    clock.now += 61
    limiter.acquire("new", 1, 60)
    assert list(limiter._buckets) == ["new"]


def _request(headers: dict[str, str], peer: str = "10.0.0.9") -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (peer, 1234),
        }
    )


def test_stated_address_needs_the_right_secret(monkeypatch):
    monkeypatch.setenv("PROXY_SHARED_SECRET", "s3cret")
    stated = {"X-Client-Address": "203.0.113.7", "X-Forwarded-For": "198.51.100.1"}
    assert client_address(_request({**stated, "X-Proxy-Secret": "s3cret"})) == "203.0.113.7"
    assert client_address(_request({**stated, "X-Proxy-Secret": "wrong"})) == "198.51.100.1"
    assert client_address(_request(stated)) == "198.51.100.1"


def test_no_secret_configured_never_trusts_the_stated_address(monkeypatch):
    monkeypatch.delenv("PROXY_SHARED_SECRET", raising=False)
    request = _request({"X-Client-Address": "203.0.113.7", "X-Proxy-Secret": ""})
    assert client_address(request) == "10.0.0.9"


def test_only_the_rightmost_forwarded_entry_counts(monkeypatch):
    monkeypatch.delenv("PROXY_SHARED_SECRET", raising=False)
    request = _request({"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 198.51.100.1"})
    assert client_address(request) == "198.51.100.1"
    assert client_address(_request({"X-Forwarded-For": "garbage"})) == "10.0.0.9"


class FakeAuth:
    def __init__(self):
        self.checked = 0
        self.blocked: list[tuple[str, str]] = []

    def login(self, _username, password):
        self.checked += 1
        return "token" if password == "right" else None

    def record_login_blocked(self, scope, address):
        self.blocked.append((scope, address))

    def user_from_token(self, _token):
        return AuthenticatedUser(1, "u", "compliance", frozenset({"rule:edit"}))


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "rate-limit-tests-secret-that-is-long-enough")
    app = create_app()
    auth = FakeAuth()
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_detection_service] = lambda: SimpleNamespace(
        evaluate=lambda actor_id: 0
    )
    return TestClient(app), auth


def _login(client, username="ayse", password="wrong", address="198.51.100.1"):
    return client.post(
        "/auth/login",
        data={"username": username, "password": password},
        headers={"X-Forwarded-For": address},
    )


def test_login_blocks_the_pair_before_checking_the_password(api):
    client, auth = api
    assert [_login(client).status_code for _ in range(LOGIN_PAIR_LIMIT)] == [401] * LOGIN_PAIR_LIMIT
    response = _login(client)
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert auth.checked == LOGIN_PAIR_LIMIT
    _login(client)
    assert auth.blocked == [("account_address", "198.51.100.1")]


def test_blocked_pair_does_not_lock_out_the_real_user(api):
    client, _ = api
    for _ in range(LOGIN_PAIR_LIMIT + 1):
        _login(client)
    assert _login(client, password="right", address="203.0.113.7").status_code == 200
    assert _login(client, username="mehmet").status_code == 401


def test_success_clears_the_pair_count(api):
    client, _ = api
    for _ in range(LOGIN_PAIR_LIMIT - 1):
        _login(client)
    assert _login(client, password="right").status_code == 200
    assert [_login(client).status_code for _ in range(LOGIN_PAIR_LIMIT)] == [401] * LOGIN_PAIR_LIMIT


def test_spraying_many_accounts_is_limited_per_address(api):
    client, auth = api
    for index in range(LOGIN_ADDRESS_LIMIT):
        assert _login(client, username=f"user{index}").status_code == 401
    assert _login(client, username="another").status_code == 429
    assert auth.blocked == [("address", "198.51.100.1")]


def test_a_broken_password_check_is_not_counted(api):
    client, auth = api
    client = TestClient(client.app, raise_server_exceptions=False)
    healthy_login, auth.login = auth.login, lambda *_: (_ for _ in ()).throw(RuntimeError("db"))
    assert [_login(client).status_code for _ in range(LOGIN_PAIR_LIMIT + 2)] == [503] * (LOGIN_PAIR_LIMIT + 2)
    auth.login = healthy_login
    assert _login(client, password="right").status_code == 200


def _signed_in() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(1)}"}


def test_every_authenticated_endpoint_has_the_general_cap(api):
    client, _ = api
    headers = _signed_in()
    limit = GENERAL_RATE[0]
    assert all(client.get("/auth/me", headers=headers).status_code == 200 for _ in range(limit))
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 429 and "Retry-After" in response.headers


def test_costly_endpoint_has_its_own_limit(api):
    client, _ = api
    headers = _signed_in()
    limit = RULE_EVALUATION_RATE[0]
    assert all(client.post("/rules/evaluate", headers=headers).status_code == 200 for _ in range(limit))
    assert client.post("/rules/evaluate", headers=headers).status_code == 429
    assert client.get("/auth/me", headers=headers).status_code == 200


def test_requests_without_a_valid_login_are_capped_per_address(api):
    client, _ = api
    limit = ANONYMOUS_ADDRESS_RATE[0]
    caller = {"X-Forwarded-For": "198.51.100.1"}
    assert all(client.get("/auth/me", headers=caller).status_code == 401 for _ in range(limit))
    response = client.get("/auth/me", headers=caller)
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    # A forged token is still anonymous; another address and a real login are not affected.
    forged = client.get("/auth/me", headers={**caller, "Authorization": "Bearer forged"})
    assert forged.status_code == 429
    assert client.get("/auth/me", headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 401
    assert client.get("/auth/me", headers={**caller, **_signed_in()}).status_code == 200


def test_oversized_body_is_refused_before_login_runs(api):
    client, auth = api
    body = b"x" * (MAX_BODY_BYTES + 1)
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    declared = client.post("/auth/login", content=body, headers=form)
    assert declared.status_code == 413

    def chunks():
        yield body[: MAX_BODY_BYTES // 2]
        yield body[MAX_BODY_BYTES // 2 :]

    undeclared = client.post("/auth/login", content=chunks(), headers=form)
    assert undeclared.status_code == 413
    assert auth.checked == 0


def test_uploads_may_be_larger_than_other_requests(api):
    client, _ = api
    headers = {"Content-Type": "text/csv"}
    allowed = client.post("/uploads", content=b"x" * (MAX_BODY_BYTES + 1), headers=headers)
    assert allowed.status_code != 413
    too_big = client.post("/uploads", content=b"x" * (MAX_UPLOAD_BODY_BYTES + 1), headers=headers)
    assert too_big.status_code == 413


def test_login_is_turned_away_while_every_password_slot_is_busy(api):
    client, auth = api
    for _ in range(MAX_CONCURRENT_PASSWORD_CHECKS):
        assert password_checks.acquire(blocking=False)
    try:
        attempts = [_login(client) for _ in range(LOGIN_PAIR_LIMIT + 2)]
    finally:
        for _ in range(MAX_CONCURRENT_PASSWORD_CHECKS):
            password_checks.release()
    assert {response.status_code for response in attempts} == {503}
    assert attempts[0].headers["Retry-After"] == "5"
    assert auth.checked == 0
    # Being turned away is not a failed guess, and the slots come back.
    assert _login(client, password="right").status_code == 200
