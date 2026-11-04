"""Dashboards (K3), audit log, rule reason (K5), uploads (K13), users, system, K12."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from backend.models import AuditLog, Transaction, UploadBatch, UploadRowError


def test_dashboard_summary_days_and_validation(client, users):
    headers = users["compliance"]["headers"]
    body = client.get("/dashboard/summary", params={"days": 7}, headers=headers).json()
    assert body["days"] == 7 and len(body["trends"]) == 7
    assert body["trends"][-1]["date"] == date.today().isoformat()
    assert client.get("/dashboard/summary", params={"days": 5}, headers=headers).status_code == 422


def test_funnel_adds_up(client, users, factory):
    customer = factory.customer()
    factory.alert(customer, status="closed")                       # analyst closed
    factory.alert(customer, rule_code="R01")                      # analyst open
    confirmed = factory.alert(customer, rule_code="R06", status="confirmed_suspicious")
    factory.history(confirmed, users["analyst"]["user_id"], "new", "in_review")
    returned = factory.alert(customer, rule_code="R07", status="new")
    factory.history(returned, users["analyst"]["user_id"], "new", "in_review")
    factory.history(returned, users["compliance"]["user_id"], "in_review", "new")
    factory.commit()
    body = client.get("/dashboard/funnel", params={"days": 7}, headers=users["analyst"]["headers"]).json()
    assert body["created"] == body["analyst_closed"] + body["analyst_open"] + body["escalated"]
    assert body["escalation_outcome"]["confirmed"] >= 1
    assert body["escalation_outcome"]["returned"] >= 1
    outcome = body["escalation_outcome"]
    assert body["escalated"] == outcome["confirmed"] + outcome["closed"] + outcome["returned"] + outcome["pending"]


def test_rule_performance_hit_rate(client, users, factory):
    customer = factory.customer()
    factory.alert(customer, rule_code="R13", status="confirmed_suspicious")
    factory.alert(customer, rule_code="R13", status="closed")
    factory.alert(customer, rule_code="R13", status="closed")
    factory.commit()
    rows = client.get("/dashboard/rule-performance", params={"days": 7}, headers=users["analyst"]["headers"]).json()
    r13 = next(row for row in rows if row["rule_code"] == "R13")
    assert r13["confirmed"] >= 1 and r13["closed"] >= 2
    assert 0 < r13["hit_rate"] < 1


def test_audit_log_filters_names_and_redaction(client, users, factory):
    customer = factory.customer()
    alert = factory.alert(customer)
    factory.commit()
    # View the customer while the alert is new, then escalate.
    client.get(f"/alerts/{alert.alert_id}/customer-context", headers=users["analyst"]["headers"])
    client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "in_review", "note": "Gizli inceleme notu"},
        headers=users["analyst"]["headers"],
    )
    actor = users["analyst"]["user_id"]

    compliance = client.get(
        "/audit-log",
        params={"actor_id": actor, "exclude_action": "customer.viewed"},
        headers=users["compliance"]["headers"],
    ).json()
    assert {item["action"] for item in compliance["items"]} == {"alert.status_changed"}
    item = compliance["items"][0]
    assert item["actor_name"] == users["analyst"]["username"] and item["actor_role"] == "analyst"
    assert item["details"]["note"] == "Gizli inceleme notu"

    viewed = client.get(
        "/audit-log", params={"actor_id": actor, "action": "customer.viewed"}, headers=users["compliance"]["headers"]
    ).json()["items"]
    assert viewed[0]["entity_id"] == customer.customer_no

    # The administrator has every permission during development, so nothing is redacted.
    admin = client.get("/audit-log", params={"actor_id": actor}, headers=users["admin"]["headers"]).json()["items"]
    assert "Gizli inceleme notu" in str(admin)
    assert client.get(
        "/audit-log", params={"date_from": "2026-02-01", "date_to": "2026-01-01"}, headers=users["admin"]["headers"]
    ).status_code == 422


def test_rule_change_requires_a_reason(client, users, session):
    headers = users["compliance"]["headers"]
    rule = client.get("/rules", headers=headers).json()
    r05 = next(item for item in rule if item["rule_code"] == "R05")
    body = {"is_active": r05["is_active"], "weight": "0.5", "thresholds": r05["thresholds"]}
    assert client.put("/rules/R05", json=body, headers=headers).status_code == 422
    assert client.put("/rules/R05", json={**body, "reason": "   "}, headers=headers).status_code == 422
    response = client.put("/rules/R05", json={**body, "reason": "Kurum onayı 2026/14"}, headers=headers)
    assert response.status_code == 200, response.text
    audit = session.scalars(
        select(AuditLog).where(AuditLog.action == "rule.updated", AuditLog.actor_id == users["compliance"]["user_id"])
    ).one()
    assert audit.details["reason"] == "Kurum onayı 2026/14"
    assert client.post("/rules/evaluate", headers=users["analyst"]["headers"]).status_code == 403


def test_upload_rows_only_for_the_uploader(client, users, session):
    def batch(owner):
        row = UploadBatch(uploaded_by=owner, entity_type="customer", file_name="c.csv", total_rows=1, accepted_rows=0, rejected_rows=1)
        session.add(row)
        session.flush()
        session.add(UploadRowError(batch_id=row.batch_id, row_number=2, reason="bad income", row_data={"full_name": "Ayşe Gizli", "monthly_income": "x"}))
        session.commit()
        return row.batch_id

    other = batch(users["analyst"]["user_id"])
    mine = batch(users["admin"]["user_id"])
    headers = users["admin"]["headers"]
    foreign = client.get(f"/uploads/{other}", headers=headers).json()
    assert foreign["errors"][0] == {"row_number": 2, "reason": "bad income", "row_data": None}
    assert foreign["own_upload"] is False
    own = client.get(f"/uploads/{mine}", headers=headers).json()
    assert own["errors"][0]["row_data"]["full_name"] == "Ayşe Gizli"
    listing = client.get("/uploads", headers=headers).json()
    assert {item["batch_id"] for item in listing} >= {other, mine}
    assert next(item for item in listing if item["batch_id"] == other)["uploaded_by_name"] == users["analyst"]["username"]


def test_users_cannot_change_their_own_role_or_status(client, users):
    admin = users["admin"]
    response = client.patch(f"/users/{admin['user_id']}", json={"is_active": False}, headers=admin["headers"])
    assert response.status_code == 403
    assert response.json()["detail"] == "You cannot change your own role or status."
    other = client.patch(f"/users/{users['analyst2']['user_id']}", json={"role_code": "compliance"}, headers=admin["headers"])
    assert other.status_code == 200 and other.json()["role_code"] == "compliance"


def test_system_overview_reports_schema_head(client, users):
    health = client.get("/admin/system-overview", headers=users["admin"]["headers"]).json()["health"]
    assert health["schema_head"] == "0007_admin_all_permissions"
    assert health["schema_revision"] == health["schema_head"]


def test_transaction_summary_matches_the_database(client, users, factory, session):
    customer = factory.customer()
    own = factory.account(customer)
    other = factory.account(factory.customer("Karşı"))
    base = datetime(2031, 3, 1, 10, 0)
    for index in range(30):
        factory.transaction(own, other, f"{100 + index}.50", tx_time=base + timedelta(days=index % 10))
    for index in range(5):
        factory.transaction(other, own, "1000.00", tx_time=base + timedelta(days=index))
    factory.commit()
    headers = users["compliance"]["headers"]
    params = {"customer_no": customer.customer_no, "date_from": "2031-03-01", "date_to": "2031-03-31"}
    body = client.get("/transactions/summary", params=params, headers=headers).json()
    expected_out = session.scalar(
        select(func.sum(Transaction.amount)).where(Transaction.sender_account_id == own.account_id)
    )
    totals = body["by_currency"][0]
    assert body["transfer_count"] == 35
    assert Decimal(totals["outgoing"]) == expected_out
    assert Decimal(totals["incoming"]) == Decimal("5000.00")
    assert (totals["count"], totals["incoming_count"], totals["outgoing_count"]) == (35, 5, 30)
    assert body["timeline"]["granularity"] == "day"
    assert sum(point["count"] for point in body["timeline"]["points"]) == 35
    outgoing_route = next(route for route in body["routes"] if route["sender_is_focus"])
    assert outgoing_route["count"] == 30 and not outgoing_route["receiver_is_focus"]
    assert body["routes"][0]["amount"] == "5000.00"  # ordered by amount
    assert own.account_no not in str(body)
    views = session.scalars(
        select(AuditLog).where(AuditLog.action == "customer.viewed", AuditLog.actor_id == users["compliance"]["user_id"])
    ).all()
    assert [v.details["source"] for v in views] == ["transaction_analysis"]
    no_focus = client.get("/transactions/summary", params={"date_from": "2031-03-01", "date_to": "2031-03-31"}, headers=headers).json()
    assert no_focus["by_currency"][0]["incoming"] is None
    assert client.get("/transactions/summary", headers=users["analyst"]["headers"]).status_code == 403
