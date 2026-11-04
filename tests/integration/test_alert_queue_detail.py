"""K1 queue, K8 explanation, K9 re-alerting, K13 masking (PostgreSQL)."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from backend.detection.evaluation import DetectionEvaluation
from backend.detection.metadata import RuleResultEvidence
from backend.models import Alert, AlertTransaction, AuditLog, MonitoringRule
from backend.repositories.detection_repository import SqlAlchemyDetectionRepository


def _token() -> str:
    return "Zq" + uuid4().hex[:8]


def test_queue_groups_by_customer_and_summarises_all_pages(client, users, factory):
    token = _token()
    base = datetime(2026, 10, 1, 9, 0)
    expected_alerts = 0
    for index in range(7):
        customer = factory.customer(f"{token} Müşteri{index}")
        for offset in range(1 + index % 2):  # 1 or 2 alerts per customer
            factory.alert(
                customer,
                rule_code=("R01", "R05")[offset],
                score="0.9500" if index == 6 else "0.6000",
                created_at=base + timedelta(days=index, hours=offset),
            )
            expected_alerts += 1
    factory.commit()
    response = client.get(
        "/alerts/queue",
        params={"q": token, "limit": 3},
        headers=users["analyst"]["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 7
    assert len(body["items"]) == 3
    assert body["summary"]["alerts"] == expected_alerts
    assert body["summary"]["customers"] == 7
    assert body["summary"]["high_customers"] == 1
    # high severity first, then oldest alert
    assert body["items"][0]["customer_name"] == f"{token} Müşteri6"
    assert body["items"][0]["severity"] == "high"
    assert body["items"][1]["customer_name"] == f"{token} Müşteri0"
    two_alert_group = next(i for i in body["items"] if i["alert_count"] == 2)
    assert two_alert_group["rule_codes"] == ["R01", "R05"]
    assert two_alert_group["customer_type"] == "BIREYSEL"
    # stable order across identical requests
    again = client.get(
        "/alerts/queue",
        params={"q": token, "limit": 3},
        headers=users["analyst"]["headers"],
    ).json()
    assert [i["customer_no"] for i in again["items"]] == [
        i["customer_no"] for i in body["items"]
    ]


def test_queue_search_finds_customer_on_any_page(client, users, factory):
    token = _token()
    for index in range(5):
        factory.alert(factory.customer(f"{token} Kişi{index}"))
    target = factory.customer(f"{token} Ahmet Yılmazoğlu")
    factory.alert(target, created_at=datetime(2030, 1, 1))  # newest -> last page
    factory.commit()
    response = client.get(
        "/alerts/queue",
        params={"q": f"{token} ahmet yılmaz"},
        headers=users["analyst"]["headers"],
    ).json()
    assert [item["customer_no"] for item in response["items"]] == [target.customer_no]


def test_queue_shows_who_returned_the_case(client, users, factory):
    token = _token()
    customer = factory.customer(f"{token} İade")
    alert = factory.alert(customer, status="in_review")
    factory.history(alert, users["analyst"]["user_id"], "new", "in_review")
    factory.commit()
    client.patch(
        f"/alerts/{alert.alert_id}/status",
        json={"status": "new", "note": "Eksik"},
        headers=users["compliance"]["headers"],
    )
    body = client.get(
        "/alerts/queue", params={"q": token}, headers=users["analyst"]["headers"]
    ).json()
    item = body["items"][0]
    assert item["returned_by"] == users["compliance"]["username"]
    assert item["returned_note"] == "Eksik"
    assert body["summary"]["returned_customers"] == 1


def test_compliance_waiting_sort(client, users, factory):
    token = _token()
    early = factory.customer(f"{token} Erken")
    late = factory.customer(f"{token} Geç")
    for customer, when in ((late, datetime(2026, 10, 5)), (early, datetime(2026, 10, 1))):
        alert = factory.alert(customer, status="in_review", score="0.9500")
        factory.history(alert, users["analyst"]["user_id"], "new", "in_review", at=when)
    factory.commit()
    body = client.get(
        "/alerts/queue",
        params={"q": token, "status": "in_review", "sort": "waiting"},
        headers=users["compliance"]["headers"],
    ).json()
    assert [i["customer_name"] for i in body["items"]] == [
        f"{token} Erken",
        f"{token} Geç",
    ]


def _alert_with_transaction(factory):
    customer = factory.customer("Ahmet Yılmaz")
    counterparty = factory.customer("Ömer Faruk Kılıç")
    company = factory.customer("Nehir Lojistik A.Ş.", customer_type="KURUMSAL")
    own = factory.account(customer)
    other = factory.account(counterparty, account_no="TR000000000000000000007781")
    company_account = factory.account(company)
    out_tx = factory.transaction(own, other, "45000.00")
    in_tx = factory.transaction(company_account, own, "1000.00")
    alert = factory.alert(customer, transactions=[out_tx, in_tx])
    factory.commit()
    return alert


def test_analyst_alert_detail_masks_counterparties(client, users, factory):
    alert = _alert_with_transaction(factory)
    response = client.get(f"/alerts/{alert.alert_id}", headers=users["analyst"]["headers"])
    assert response.status_code == 200
    body = response.json()
    text = response.text
    assert "Ömer Faruk Kılıç" not in text
    assert "TR000000000000000000007781" not in text
    for forbidden in ("sender_customer_name", "receiver_customer_name", "sender_account_no"):
        assert forbidden not in text
    out_tx, in_tx = body["transactions"]
    assert out_tx["view"] == "masked" and out_tx["direction"] == "out"
    assert out_tx["counterparty"] == "Ö. F. Kılıç"
    assert out_tx["counterparty_account"] == "…7781"
    assert in_tx["counterparty"] == "Nehir L. A."


def test_compliance_alert_detail_is_full(client, users, factory):
    alert = _alert_with_transaction(factory)
    body = client.get(
        f"/alerts/{alert.alert_id}", headers=users["compliance"]["headers"]
    ).json()
    assert body["transactions"][0]["view"] == "full"
    assert body["transactions"][0]["receiver_customer_name"] == "Ömer Faruk Kılıç"


def _evidence(customer_id, score, transactions=(), rule_code="R05"):
    return RuleResultEvidence(
        rule_code=rule_code,
        customer_id=customer_id,
        customer_type="BIREYSEL",
        parameter_snapshot={
            "status": "PROVISIONAL",
            "values": {"x_esik": "4", "x_kesin": "6", "history_min": 20},
        },
        parameter_status="PROVISIONAL",
        result_status="evaluated",
        raw_x=Decimal("5.4123"),
        score=Decimal(score),
        step_trace=[
            {"step": 1, "text": "Geçmişi topla", "status": "completed", "details": {"history_count": 64}},
            {"step": 2, "text": "Skorla", "status": "completed", "details": {"maximum_z": "5.41", "score": score}},
        ],
        transactions=list(transactions),
        alert_mode="ALERT",
    )


def _rules(session):
    return {rule.rule_code: rule for rule in session.scalars(select(MonitoringRule))}


def _persist(session, as_of, results):
    return SqlAlchemyDetectionRepository(session).persist_run(
        uuid4(),
        as_of,
        DetectionEvaluation(results=results, summary={"rules": {}}),
        _rules(session),
    )


def _alerts_for(session, customer_id):
    session.expire_all()
    return session.scalars(
        select(Alert).where(Alert.customer_id == customer_id).order_by(Alert.alert_id)
    ).all()


def test_k9_open_alert_is_reused_and_rescored(session, factory):
    customer = factory.customer()
    account = factory.account(customer)
    other = factory.account(factory.customer("Karşı Taraf"))
    first_tx = factory.transaction(account, other, "100.00")
    second_tx = factory.transaction(account, other, "200.00")
    factory.commit()
    day1 = datetime(2026, 11, 2, 2, 0)
    assert _persist(session, day1, [_evidence(customer.customer_id, "0.7500", [first_tx])]) == 1
    assert _persist(
        session, day1 + timedelta(days=1), [_evidence(customer.customer_id, "0.9200", [second_tx])]
    ) == 0
    alerts = _alerts_for(session, customer.customer_id)
    assert len(alerts) == 1
    assert alerts[0].score == Decimal("0.9200") and alerts[0].severity == "high"
    linked = session.scalars(
        select(AlertTransaction.transaction_id).where(
            AlertTransaction.alert_id == alerts[0].alert_id
        )
    ).all()
    assert set(linked) == {first_tx.transaction_id, second_tx.transaction_id}
    rescored = session.scalars(
        select(AuditLog).where(
            AuditLog.action == "alert.rescored",
            AuditLog.entity_id == str(alerts[0].alert_id),
        )
    ).all()
    assert len(rescored) == 1 and rescored[0].details["new_score"] == "0.9200"
    # Same data again: nothing new, no extra rescore.
    assert _persist(
        session, day1 + timedelta(days=2), [_evidence(customer.customer_id, "0.9200", [second_tx])]
    ) == 0
    assert len(_alerts_for(session, customer.customer_id)) == 1


def test_k9_new_alert_after_close_even_on_the_same_day(session, factory):
    customer = factory.customer()
    factory.commit()
    day = datetime(2026, 11, 3, 2, 0)
    _persist(session, day, [_evidence(customer.customer_id, "0.8000")])
    alert = _alerts_for(session, customer.customer_id)[0]
    alert.status = "closed"
    session.commit()
    assert _persist(session, day, [_evidence(customer.customer_id, "0.8000")]) == 1
    alerts = _alerts_for(session, customer.customer_id)
    assert [a.status for a in alerts] == ["closed", "new"]
    assert alerts[1].deduplication_key.endswith(":2")
    # an alert without evidence transactions is still created
    assert alerts[1].transactions == []


def test_k9_rescore_keeps_a_raised_severity(session, factory):
    customer = factory.customer()
    alert = factory.alert(customer, score="0.6000", severity="high")  # e.g. raised by R17
    factory.commit()
    _persist(session, datetime(2026, 11, 3), [_evidence(customer.customer_id, "0.7500")])
    session.refresh(alert)
    assert alert.score == Decimal("0.7500") and alert.severity == "high"


def test_k8_explanation_comes_from_the_scoring_run(client, users, session, factory):
    customer = factory.customer()
    factory.commit()
    _persist(session, datetime(2026, 11, 3, 2, 0), [_evidence(customer.customer_id, "0.8127")])
    alert = _alerts_for(session, customer.customer_id)[0]
    body = client.get(f"/alerts/{alert.alert_id}", headers=users["analyst"]["headers"]).json()
    explanation = body["explanation"]
    assert explanation["score"] == body["score"]
    assert explanation["parameter_status"] == "PROVISIONAL"
    assert explanation["x_esik"] == "4" and explanation["x_kesin"] == "6"
    assert [step["step"] for step in explanation["steps"]] == [1, 2]
    assert explanation["steps"][0]["details"]["history_count"] == 64


def test_k8_legacy_rule_alert_has_no_explanation(client, users, factory):
    alert = factory.alert(factory.customer(), rule_code="R1")
    factory.commit()
    body = client.get(f"/alerts/{alert.alert_id}", headers=users["analyst"]["headers"]).json()
    assert body["explanation"] is None
