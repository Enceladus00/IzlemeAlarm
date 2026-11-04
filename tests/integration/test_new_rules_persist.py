"""R17 and R18 persistence against PostgreSQL."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from backend.detection.evaluation import DetectionEvaluation
from backend.detection.metadata import RuleResultEvidence
from backend.models import Alert, AuditLog, MonitoringRule, RuleResult
from backend.repositories.detection_repository import SqlAlchemyDetectionRepository

R17_VALUES = {"window_days": 30, "min_rules": 2, "excluded_rules": ["R02", "R17", "R18"], "open_statuses": ["new", "in_review"]}


def _rules(session):
    return {rule.rule_code: rule for rule in session.scalars(select(MonitoringRule))}


def _r17(customer_id):
    return RuleResultEvidence(
        rule_code="R17",
        customer_id=customer_id,
        customer_type="BIREYSEL",
        parameter_snapshot={"status": "PROVISIONAL", "values": R17_VALUES},
        parameter_status="PROVISIONAL",
        result_status="evaluated",
        raw_x=None,
        score=None,
        step_trace=[{"step": i, "text": "t", "status": "pending_persist", "details": {}} for i in (1, 2, 3)],
        transactions=[],
        alert_mode="SEVERITY_RAISE",
    )


def _persist(session, results, as_of=datetime(2026, 11, 4, 2, 0)):
    return SqlAlchemyDetectionRepository(session).persist_run(
        uuid4(), as_of, DetectionEvaluation(results=results, summary={"rules": {}}), _rules(session)
    )


def test_r17_raises_open_alerts_once_when_k_reaches_min_rules(session, factory):
    customer = factory.customer()
    first = factory.alert(customer, rule_code="R01", score="0.6000", created_at=datetime(2026, 11, 1))
    second = factory.alert(customer, rule_code="R05", score="0.7500", created_at=datetime(2026, 11, 2))
    excluded = factory.alert(customer, rule_code="R02", score="0.9500", created_at=datetime(2026, 11, 2))
    factory.commit()
    _persist(session, [_r17(customer.customer_id)])
    for alert in (first, second, excluded):
        session.refresh(alert)
    assert (first.severity, second.severity) == ("medium", "high")
    assert excluded.severity == "high"  # already high: nothing to raise
    events = session.scalars(
        select(AuditLog).where(
            AuditLog.action == "alert.severity_raised",
            AuditLog.entity_id.in_([str(first.alert_id), str(second.alert_id)]),
        )
    ).all()
    assert len(events) == 2 and {e.details["K"] for e in events} == {2}
    trace = session.scalars(
        select(RuleResult.step_trace).where(RuleResult.customer_id == customer.customer_id)
    ).one()
    assert trace[0]["details"]["K"] == 2 and trace[0]["details"]["counted_rules"] == ["R01", "R05"]

    # A second run does not raise the same alerts again.
    _persist(session, [_r17(customer.customer_id)])
    session.refresh(first)
    assert first.severity == "medium"


def test_r17_below_min_rules_changes_nothing(session, factory):
    customer = factory.customer()
    only = factory.alert(customer, rule_code="R01", score="0.6000", created_at=datetime(2026, 11, 1))
    factory.commit()
    _persist(session, [_r17(customer.customer_id)])
    session.refresh(only)
    assert only.severity == "low"


def test_r18_score_above_one_is_capped_and_persisted(session, factory):
    customer = factory.customer()
    factory.commit()
    result = RuleResultEvidence(
        rule_code="R18",
        customer_id=customer.customer_id,
        customer_type="BIREYSEL",
        parameter_snapshot={"status": "PROVISIONAL", "values": {"p": "4", "alert_threshold": "0.5"}},
        parameter_status="PROVISIONAL",
        result_status="evaluated",
        raw_x=Decimal("1.0000"),
        score=Decimal("1.0000"),
        step_trace=[],
        transactions=[],
        alert_mode="ALERT",
        alert_threshold=Decimal("0.5"),
    )
    assert _persist(session, [result]) == 1
    alert = session.scalars(select(Alert).where(Alert.customer_id == customer.customer_id)).one()
    assert alert.score == Decimal("1.0000") and alert.severity == "high"


def test_r18_respects_its_own_alert_threshold(session, factory):
    customer = factory.customer()
    factory.commit()
    result = RuleResultEvidence(
        rule_code="R18",
        customer_id=customer.customer_id,
        customer_type="BIREYSEL",
        parameter_snapshot={"status": "PROVISIONAL", "values": {"p": "4", "alert_threshold": "0.8"}},
        parameter_status="PROVISIONAL",
        result_status="evaluated",
        raw_x=Decimal("0.7000"),
        score=Decimal("0.7000"),
        step_trace=[],
        transactions=[],
        alert_mode="ALERT",
        alert_threshold=Decimal("0.8"),
    )
    assert _persist(session, [result]) == 0
