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
