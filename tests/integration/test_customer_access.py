"""K4 customer context, K6 view logging (PostgreSQL)."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from backend.models import AuditLog


def _views(session, actor_id):
    session.expire_all()
    return session.scalars(
        select(AuditLog)
        .where(AuditLog.action == "customer.viewed", AuditLog.actor_id == actor_id)
        .order_by(AuditLog.audit_id)
    ).all()


def _customer_with_history(factory, status="new"):
    customer = factory.customer("Ahmet Yılmaz", created_at=datetime(2019, 5, 1))
    own = factory.account(customer, account_no="TR000000000000000000004410")
    eur = factory.account(customer, currency="EUR")
    other = factory.account(factory.customer("Ömer Kılıç"), account_no="TR000000000000000000007781")
    now = datetime.now()
    recent_out = factory.transaction(own, other, "45000.00", tx_time=now - timedelta(days=2))
    factory.transaction(other, own, "12000.00", tx_time=now - timedelta(days=3))
    factory.transaction(eur, other, "500.00", currency="EUR", tx_time=now - timedelta(days=4))
    factory.transaction(own, other, "999.00", tx_time=now - timedelta(days=240))  # > 6 months
    alert = factory.alert(customer, status=status, transactions=[recent_out])
    factory.commit()
    return customer, alert, recent_out


def test_analyst_gets_masked_six_month_context_for_new_alert(client, users, factory, session):
    customer, alert, recent_out = _customer_with_history(factory)
    response = client.get(
        f"/alerts/{alert.alert_id}/customer-context", headers=users["analyst"]["headers"]
    )
    assert response.status_code == 200, response.text
    text = response.text
    for forbidden in ("full_name", "account_no", "receiver_customer_name", "Ömer Kılıç",
                      "TR000000000000000000004410", "999.00"):
        assert forbidden not in text
    body = response.json()
    assert body["profile"] == {
        "customer_type": "BIREYSEL",
        "occupation": "Öğretmen",
        "monthly_income": "28000.00",
        "risk_level": "medium",
        "customer_since": 2019,
    }
    assert {"account": "…4410", "currency": "TRY", "type": "current"} in body["accounts"]
    assert len(body["transactions"]) == 3
    first = body["transactions"][0]
    assert first["counterparty"] == "Ö. Kılıç" and first["counterparty_account"] == "…7781"
    assert first["in_alert"] is True and first["direction"] == "out"
    summary = {row["currency"]: row for row in body["summary"]}
    assert summary["TRY"]["outgoing_30d"] == "45000.00"
    assert summary["TRY"]["incoming_30d"] == "12000.00"
    assert summary["EUR"]["outgoing_30d"] == "500.00"
    views = _views(session, users["analyst"]["user_id"])
    assert [(v.entity_id, v.details["source"]) for v in views] == [
        (customer.customer_no, "alert_detail")
    ]


def test_analyst_cannot_open_context_of_non_new_alert(client, users, factory):
    _customer, alert, _tx = _customer_with_history(factory, status="closed")
    denied = client.get(
        f"/alerts/{alert.alert_id}/customer-context", headers=users["analyst"]["headers"]
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Customer information is only available for open alerts."
    allowed = client.get(
        f"/alerts/{alert.alert_id}/customer-context", headers=users["compliance"]["headers"]
    )
    assert allowed.status_code == 200


def test_repeated_views_within_30_minutes_are_logged_once(client, users, factory, session):
    _customer, alert, _tx = _customer_with_history(factory)
    for _ in range(3):
        client.get(
            f"/alerts/{alert.alert_id}/customer-context", headers=users["analyst"]["headers"]
        )
    assert len(_views(session, users["analyst"]["user_id"])) == 1


def test_no_data_when_the_view_cannot_be_logged(client, users, factory, monkeypatch):
    _customer, alert, _tx = _customer_with_history(factory)

    def broken_select(*_args, **_kwargs):
        raise OperationalError("SELECT", {}, Exception("audit storage unavailable"))

    monkeypatch.setattr("backend.repositories.customer_view_log.select", broken_select)
    response = client.get(
        f"/alerts/{alert.alert_id}/customer-context", headers=users["analyst"]["headers"]
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Could not record the customer data access."}
    transactions = client.get(
        "/transactions",
        params={"customer_no": _customer.customer_no},
        headers=users["compliance"]["headers"],
    )
    assert transactions.status_code == 503
    assert "Ahmet" not in transactions.text


def test_transaction_analysis_logs_the_viewed_customers(client, users, factory, session):
    customer, _alert, _tx = _customer_with_history(factory)
    headers = users["compliance"]["headers"]
    actor = users["compliance"]["user_id"]
    assert client.get(
        "/transactions", params={"customer_no": customer.customer_no}, headers=headers
    ).status_code == 200
    assert [v.entity_id for v in _views(session, actor)] == [customer.customer_no]

    # by account number -> the owner is logged
    other = factory.customer("Hesap Sahibi")
    account = factory.account(other)
    factory.transaction(account, account, "10.00", tx_time=datetime(2031, 1, 1))
    factory.commit()
    client.get("/transactions", params={"account_no": account.account_no}, headers=headers)
    assert other.customer_no in {v.entity_id for v in _views(session, actor)}

    # no customer filter -> every customer on the returned page is logged
    third = factory.customer("Üçüncü Kişi")
    fourth = factory.customer("Dördüncü Kişi")
    factory.transaction(
        factory.account(third), factory.account(fourth), "10.00", tx_time=datetime(2032, 1, 1)
    )
    factory.commit()
    client.get(
        "/transactions",
        params={"date_from": "2032-01-01", "date_to": "2032-01-01"},
        headers=headers,
    )
    logged = {v.entity_id for v in _views(session, actor)}
    assert {third.customer_no, fourth.customer_no} <= logged


def test_removed_endpoints_are_gone(client, users, factory):
    _customer, alert, _tx = _customer_with_history(factory)
    assert client.get(
        f"/alerts/{alert.alert_id}/customer-transactions",
        headers=users["compliance"]["headers"],
    ).status_code == 404
    assert client.get(
        "/customers/C-1/transactions", headers=users["compliance"]["headers"]
    ).status_code == 404
