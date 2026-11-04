"""K13 redaction for audit readers without alert/customer access (kept for when
the administrator's permissions are narrowed again; see alembic 0007)."""

from backend.services.audit_service import REDACTED, redact


def test_reader_without_alert_or_customer_access_sees_no_content():
    entity, details = redact("alert.status_changed", "12", {"note": "secret", "new_status": "closed"}, frozenset({"audit:view"}))
    assert entity == "12" and details == {"note": REDACTED, "new_status": "closed"}
    entity, _ = redact("customer.viewed", "C-1042", {"source": "alert_detail"}, frozenset({"audit:view"}))
    assert entity == REDACTED


def test_reader_with_access_sees_everything():
    permissions = frozenset({"audit:view", "alert:view", "customer:view"})
    assert redact("alert.status_changed", "12", {"note": "n"}, permissions) == ("12", {"note": "n"})
    assert redact("customer.viewed", "C-1042", {}, permissions) == ("C-1042", {})
