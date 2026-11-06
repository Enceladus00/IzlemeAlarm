"""Alert workflow (7.1) and atomic bulk decisions (K2) against PostgreSQL."""

from sqlalchemy import select

from backend.models import Alert, AlertStatusHistory, AuditLog


def _status(session, alert_id: int) -> str:
    session.expire_all()
    return session.scalar(select(Alert.status).where(Alert.alert_id == alert_id))


def _setup_alert(factory, status="new"):
    customer = factory.customer()
    alert = factory.alert(customer, status=status)
    factory.commit()
    return customer, alert


def test_analyst_cannot_confirm_and_the_denial_is_audited(client, users, factory, session):
    _customer, alert = _setup_alert(factory)
    response = client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "confirmed_suspicious", "note": "kesin"},
        headers=users["analyst"]["headers"],
    )
    assert response.status_code == 403
    assert _status(session, alert.alert_id) == "new"
    denied = session.scalars(
        select(AuditLog)
        .where(
            AuditLog.action == "ACCESS_DENIED",
            AuditLog.actor_id == users["analyst"]["user_id"],
        )
        .order_by(AuditLog.audit_id)
    ).all()
    assert denied and denied[-1].actor_id == users["analyst"]["user_id"]
    assert denied[-1].details["target_status"] == "confirmed_suspicious"


def test_analyst_escalates_and_compliance_confirms(client, users, factory, session):
    _customer, alert = _setup_alert(factory)
    escalate = client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "in_review", "note": "Profil dışı işlem"},
        headers=users["analyst"]["headers"],
    )
    assert escalate.status_code == 200, escalate.text
    assert escalate.json() == {"alert_id": alert.alert_id, "status": "in_review", "changed": True}
    confirm = client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "confirmed_suspicious", "note": "Onaylandı"},
        headers=users["compliance"]["headers"],
    )
    assert confirm.status_code == 200, confirm.text
    assert _status(session, alert.alert_id) == "confirmed_suspicious"


def test_four_eyes_blocks_the_escalator(client, users, factory, session):
    customer = factory.customer()
    alert = factory.alert(customer, status="in_review")
    factory.history(alert, users["compliance"]["user_id"], "new", "in_review")
    factory.commit()
    response = client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "closed", "note": "kapat"},
        headers=users["compliance"]["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "The user who escalated this alert cannot decide on it."
    assert _status(session, alert.alert_id) == "in_review"
    # Another compliance officer may decide.
    response = client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "closed", "note": "kapat"},
        headers=users["compliance2"]["headers"],
    )
    assert response.status_code == 200


def test_return_to_analyst_shows_actor_in_history(client, users, factory, session):
    customer = factory.customer()
    alert = factory.alert(customer, status="in_review")
    factory.history(alert, users["analyst"]["user_id"], "new", "in_review")
    factory.commit()
    response = client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "new", "note": "Eksik inceleme"},
        headers=users["compliance"]["headers"],
    )
    assert response.status_code == 200
    detail = client.get(f"/alerts/{alert.alert_id}", headers=users["analyst"]["headers"]).json()
    assert detail["status"] == "new"
    assert [h["actor_name"] for h in detail["history"]] == [
        users["analyst"]["username"],
        users["compliance"]["username"],
    ]
    assert detail["history"][-1]["actor_role"] == "compliance"
    assert detail["escalated_by"]["actor_name"] == users["analyst"]["username"]


def test_transition_rules_and_note(client, users, factory, session):
    _customer, alert = _setup_alert(factory)
    # Not in the table: new -> new (note-only updates were removed).
    response = client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "new", "note": "x"},
        headers=users["compliance"]["headers"],
    )
    assert response.status_code == 422
    # Compliance has no alert:update, so it cannot close a new alert directly.
    response = client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "closed", "note": "x"},
        headers=users["compliance"]["headers"],
    )
    assert response.status_code == 403
    response = client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "in_review", "note": "   "},
        headers=users["analyst"]["headers"],
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "A note is required for every alert decision."
    assert _status(session, alert.alert_id) == "new"


def test_admin_has_every_permission_during_development(client, users, factory):
    # alembic 0007: the administrator is a "god" user for now (K13 deferred).
    _customer, alert = _setup_alert(factory)
    headers = users["admin"]["headers"]
    assert client.get("/alerts", headers=headers).status_code == 200
    assert client.get(f"/alerts/{alert.alert_id}", headers=headers).json()["transactions"] == []
    assert client.get("/transactions", params={"date_from": "2031-01-01", "date_to": "2031-01-01"}, headers=headers).status_code == 200
    me = client.get("/auth/me", headers=headers).json()
    assert {"alert:view", "alert:update", "alert:escalate", "alert:confirm", "customer:view"} <= set(me["permissions"])


def test_four_eyes_still_applies_to_the_administrator(client, users, factory, session):
    _customer, alert = _setup_alert(factory)
    headers = users["admin"]["headers"]
    assert client.patch(
        f"/alerts/{alert.alert_id}/status", json={"status": "in_review", "note": "n"}, headers=headers
    ).status_code == 200
    denied = client.patch(
        f"/alerts/{alert.alert_id}/status", json={"status": "confirmed_suspicious", "note": "n"}, headers=headers
    )
    assert denied.status_code == 403
    assert _status(session, alert.alert_id) == "in_review"


def test_bulk_decision_is_atomic_across_customers(client, users, factory, session):
    first = factory.customer("Ahmet Yılmaz")
    other = factory.customer("Ayşe Demir")
    a1 = factory.alert(first)
    a2 = factory.alert(first, rule_code="R01")
    a3 = factory.alert(other)
    factory.commit()
    response = client.post(
        "/alerts/decisions",
        json={"alert_ids": [a1.alert_id, a2.alert_id, a3.alert_id], "status": "in_review", "note": "n"},
        headers=users["analyst"]["headers"],
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Selected alerts must belong to the same customer.",
        "alert_id": a3.alert_id,
    }
    assert {_status(session, a.alert_id) for a in (a1, a2, a3)} == {"new"}
    ids = [a1.alert_id, a2.alert_id, a3.alert_id]
    assert session.scalars(
        select(AlertStatusHistory).where(AlertStatusHistory.alert_id.in_(ids))
    ).all() == []


def test_bulk_decision_four_eyes_on_one_alert_changes_nothing(client, users, factory, session):
    customer = factory.customer()
    a1 = factory.alert(customer, status="in_review")
    a2 = factory.alert(customer, rule_code="R01", status="in_review")
    factory.history(a1, users["analyst"]["user_id"], "new", "in_review")
    factory.history(a2, users["compliance"]["user_id"], "new", "in_review")
    factory.commit()
    response = client.post(
        "/alerts/decisions",
        json={"alert_ids": [a1.alert_id, a2.alert_id], "status": "confirmed_suspicious", "note": "n"},
        headers=users["compliance"]["headers"],
    )
    assert response.status_code == 403
    assert response.json()["alert_id"] == a2.alert_id
    assert {_status(session, a.alert_id) for a in (a1, a2)} == {"in_review"}


def test_valid_bulk_decision_writes_history_and_shared_decision_id(client, users, factory, session):
    customer = factory.customer()
    alerts = [factory.alert(customer, rule_code=code) for code in ("R01", "R05", "R06")]
    factory.commit()
    ids = [a.alert_id for a in alerts]
    response = client.post(
        "/alerts/decisions",
        json={"alert_ids": ids, "status": "in_review", "note": "Profil dışı"},
        headers=users["analyst"]["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["alert_ids"] == ids and body["status"] == "in_review"
    session.expire_all()
    assert len(
        session.scalars(
            select(AlertStatusHistory).where(AlertStatusHistory.alert_id.in_(ids))
        ).all()
    ) == 3
    audits = session.scalars(
        select(AuditLog).where(
            AuditLog.action == "alert.status_changed",
            AuditLog.entity_id.in_([str(i) for i in ids]),
        )
    ).all()
    assert len(audits) == 3
    assert {row.details["decision_id"] for row in audits} == {body["decision_id"]}


def test_bulk_decision_body_validation(client, users, factory):
    customer = factory.customer()
    alert = factory.alert(customer)
    factory.commit()
    headers = users["analyst"]["headers"]
    too_many = client.post(
        "/alerts/decisions",
        json={"alert_ids": list(range(1, 52)), "status": "in_review", "note": "n"},
        headers=headers,
    )
    assert too_many.status_code == 422
    duplicate = client.post(
        "/alerts/decisions",
        json={"alert_ids": [alert.alert_id, alert.alert_id], "status": "in_review", "note": "n"},
        headers=headers,
    )
    assert duplicate.status_code == 422
    missing = client.post(
        "/alerts/decisions",
        json={"alert_ids": [alert.alert_id, 999999], "status": "in_review", "note": "n"},
        headers=headers,
    )
    assert missing.status_code == 404
    assert missing.json()["alert_id"] == 999999


def test_bulk_decision_mixed_statuses(client, users, factory, session):
    customer = factory.customer()
    a1 = factory.alert(customer)
    a2 = factory.alert(customer, rule_code="R01", status="in_review")
    factory.commit()
    response = client.post(
        "/alerts/decisions",
        json={"alert_ids": [a1.alert_id, a2.alert_id], "status": "closed", "note": "n"},
        headers=users["analyst"]["headers"],
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Selected alerts must have the same status."


def test_my_summary_counts_only_my_work(client, users, factory):
    customer = factory.customer()
    a1 = factory.alert(customer)
    a2 = factory.alert(customer, rule_code="R01")
    factory.commit()
    analyst = users["analyst"]["headers"]
    client.post(
        "/alerts/decisions",
        json={"alert_ids": [a1.alert_id, a2.alert_id], "status": "in_review", "note": "n"},
        headers=analyst,
    )
    client.patch(
        f"/alerts/{a2.alert_id}/status",
        json={"status": "new", "note": "Eksik belge"},
        headers=users["compliance"]["headers"],
    )
    mine = client.get("/dashboard/my-summary", headers=analyst).json()
    assert mine["decided_today"] == 2
    assert mine["escalated_today"] == 2
    assert mine["returned_to_me"] == 1
    case = mine["returned_cases"][0]
    assert case["customer_no"] == customer.customer_no
    assert case["returned_by"] == users["compliance"]["username"]
    assert case["note"] == "Eksik belge"
    other = client.get("/dashboard/my-summary", headers=users["analyst2"]["headers"]).json()
    assert {key: other[key] for key in ("decided_today", "escalated_today", "returned_to_me", "returned_cases")} == {
        "decided_today": 0, "escalated_today": 0, "returned_to_me": 0, "returned_cases": []
    }
    assert other["escalations_30d"] == 0 and other["decisions_today"] == []
    assert client.get("/dashboard/my-summary", headers=users["admin"]["headers"]).json()["decided_today"] == 0


def test_my_summary_panel_fields(client, users, factory, session):
    from sqlalchemy import func, select

    from backend.models import Alert

    customer = factory.customer()
    confirmed = factory.alert(customer, rule_code="R06", severity="high")
    returned = factory.alert(customer, rule_code="R07")
    closed = factory.alert(customer, rule_code="R01")
    factory.commit()
    analyst = users["analyst"]["headers"]
    compliance = users["compliance"]["headers"]
    client.post(
        "/alerts/decisions",
        json={"alert_ids": [confirmed.alert_id, returned.alert_id], "status": "in_review", "note": "n"},
        headers=analyst,
    )
    client.patch(f"/alerts/{closed.alert_id}/status", json={"status": "closed", "note": "olağan"}, headers=analyst)
    client.patch(f"/alerts/{confirmed.alert_id}/status", json={"status": "confirmed_suspicious", "note": "evet"}, headers=compliance)
    client.patch(f"/alerts/{returned.alert_id}/status", json={"status": "new", "note": "eksik"}, headers=compliance)

    mine = client.get("/dashboard/my-summary", headers=analyst).json()
    outcome = mine["escalation_outcome_30d"]
    assert mine["escalations_30d"] == 2
    assert outcome == {"confirmed": 1, "closed": 0, "returned": 1, "pending": 0}
    assert sum(outcome.values()) == mine["escalations_30d"]
    assert mine["escalated_today_confirmed"] == 1
    assert mine["closed_today"] == 1
    assert mine["queue_pending"] == session.scalar(select(func.count()).select_from(Alert).where(Alert.status == "new"))
    assert mine["queue_high"] <= mine["queue_pending"]
    decisions = mine["decisions_today"]
    assert sorted(row["alert_id"] for row in decisions) == sorted([closed.alert_id, returned.alert_id, confirmed.alert_id])
    assert {row["new_status"] for row in decisions} == {"in_review", "closed"}
    assert all(row["customer_no"] == customer.customer_no for row in decisions)
