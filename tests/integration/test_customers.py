"""Customer and account lists (customer:view) and their view logging."""

from uuid import uuid4

from sqlalchemy import select

from backend.models import AuditLog


def _views(session, actor_id, source):
    session.expire_all()
    return session.scalars(
        select(AuditLog.entity_id).where(
            AuditLog.action == "customer.viewed",
            AuditLog.actor_id == actor_id,
            AuditLog.details["source"].astext == source,
        )
    ).all()


def _token():
    return "Qx" + uuid4().hex[:8]


def test_customer_list_search_filters_and_counts_without_logging(client, users, factory, session):
    token = _token()
    ahmet = factory.customer(f"{token} Ahmet", risk_level="high")
    factory.account(ahmet)
    factory.account(ahmet, currency="USD")
    factory.alert(ahmet)
    factory.alert(ahmet, rule_code="R01", status="closed")
    factory.customer(f"{token} Firma", customer_type="KURUMSAL", risk_level="low")
    factory.commit()
    headers = users["compliance"]["headers"]
    body = client.get("/customers", params={"q": token.lower()}, headers=headers).json()
    assert body["total"] == 2
    assert [item["customer_no"] for item in body["items"]] == sorted(item["customer_no"] for item in body["items"])
    first = next(item for item in body["items"] if item["customer_no"] == ahmet.customer_no)
    assert (first["account_count"], first["open_alert_count"]) == (2, 1)
    only_corporate = client.get("/customers", params={"q": token, "customer_type": "KURUMSAL"}, headers=headers).json()
    assert [item["full_name"] for item in only_corporate["items"]] == [f"{token} Firma"]
    high = client.get("/customers", params={"q": token, "risk_level": "high"}, headers=headers).json()
    assert high["total"] == 1
    assert _views(session, users["compliance"]["user_id"], "customer_list") == []


def test_customer_profile_is_logged_and_complete(client, users, factory, session):
    customer = factory.customer()
    own = factory.account(customer)
    other = factory.account(factory.customer("Karşı"))
    factory.transaction(own, other, "10.00")
    factory.transaction(other, own, "20.00")
    factory.alert(customer)
    factory.commit()
    headers = users["compliance"]["headers"]
    body = client.get(f"/customers/{customer.customer_no}", headers=headers).json()
    assert body["full_name"] == "Ahmet Yılmaz" and body["occupation"] == "Öğretmen"
    assert body["accounts"][0]["account_no"] == own.account_no
    assert body["accounts"][0]["transaction_count"] == 2
    assert body["alerts"] == {"open": 1, "total": 1, "by_status": {"new": 1}}
    assert _views(session, users["compliance"]["user_id"], "customer_profile") == [customer.customer_no]
    missing = client.get("/customers/NOPE-404", headers=headers)
    assert missing.status_code == 404 and missing.json()["detail"] == "Customer not found."


def test_account_list_logs_every_customer_on_the_page(client, users, factory, session):
    token = _token()
    first = factory.customer(f"{token} Bir")
    second = factory.customer(f"{token} İki")
    factory.account(first, currency="EUR")
    factory.account(second, currency="EUR")
    factory.account(second, currency="TRY")
    factory.commit()
    headers = users["compliance"]["headers"]
    body = client.get("/accounts", params={"q": token, "currency": "EUR"}, headers=headers).json()
    assert body["total"] == 2
    assert {item["customer_no"] for item in body["items"]} == {first.customer_no, second.customer_no}
    logged = set(_views(session, users["compliance"]["user_id"], "account_list"))
    assert logged == {first.customer_no, second.customer_no}
    by_customer = client.get("/accounts", params={"customer_no": second.customer_no}, headers=headers).json()
    assert by_customer["total"] == 2


def test_customer_lists_need_customer_view(client, users):
    analyst = users["analyst"]["headers"]
    assert client.get("/customers", headers=analyst).status_code == 403
    assert client.get("/accounts", headers=analyst).status_code == 403
    assert client.get("/customers/C-1", headers=analyst).status_code == 403
    assert client.get("/customers", headers=users["admin"]["headers"]).status_code == 200


def test_customer_analysis_income_check_and_new_counterparties(client, users, factory, session):
    from datetime import datetime, timedelta

    customer = factory.customer(monthly_income="28000.00")
    own = factory.account(customer)
    second_own = factory.account(customer)
    known = factory.account(factory.customer("Eski Tanıdık"))
    fresh = factory.account(factory.customer("Yeni Gönderen"))
    now = datetime.now()
    # Known counterparty: also seen 200 days ago (inside the 12-month lookback).
    factory.transaction(known, own, "500.00", tx_time=now - timedelta(days=200))
    factory.transaction(known, own, "21850.00", tx_time=now)
    factory.transaction(fresh, own, "100000.00", tx_time=now)
    factory.transaction(own, fresh, "3000.00", tx_time=now)
    factory.transaction(own, second_own, "99999.00", tx_time=now)  # own transfer: ignored
    factory.commit()
    headers = users["compliance"]["headers"]

    body = client.get(f"/customers/{customer.customer_no}/analysis", params={"days": 30}, headers=headers).json()
    month = now.strftime("%Y-%m")
    assert body["days"] == 30
    assert {"month": month, "currency": "TRY", "incoming": "121850.00", "outgoing": "3000.00"} in body["monthly"]
    check = body["income_check"]
    # 121.850 / 28.000 = 4,4 × (guide E12)
    assert check["ratio"] == "4.4" and check["exceeded"] is True and check["peak_direction"] == "incoming"
    incoming = {row["customer_name"]: row for row in body["counterparties"]["incoming"]}
    assert incoming["Yeni Gönderen"]["is_new"] is True
    assert incoming["Eski Tanıdık"]["is_new"] is False
    assert [row["customer_name"] for row in body["counterparties"]["incoming"]] == ["Yeni Gönderen", "Eski Tanıdık"]
    assert body["counterparties"]["outgoing"][0]["is_new"] is True
    assert all(row["account_no"] != second_own.account_no for row in body["counterparties"]["outgoing"])
    assert _views(session, users["compliance"]["user_id"], "customer_analysis") == [customer.customer_no]

    assert client.get(f"/customers/{customer.customer_no}/analysis", params={"days": 7}, headers=headers).status_code == 422
    assert client.get(f"/customers/{customer.customer_no}/analysis", headers=users["analyst"]["headers"]).status_code == 403
    assert client.get("/customers/NOPE-404/analysis", headers=headers).status_code == 404


def test_customer_analysis_without_threshold_breach(client, users, factory):
    customer = factory.customer(monthly_income="28000.00")
    own = factory.account(customer)
    other = factory.account(factory.customer("Karşı"))
    factory.transaction(other, own, "30000.00")
    factory.commit()
    check = client.get(f"/customers/{customer.customer_no}/analysis", headers=users["compliance"]["headers"]).json()["income_check"]
    assert check["ratio"] == "1.1" and check["exceeded"] is False and check["threshold"] == "3"
