from datetime import datetime
from types import SimpleNamespace

from backend.services.analysis_service import AnalysisService


def test_system_overview_includes_health_security_and_run_metrics(monkeypatch):
    last_run = SimpleNamespace(
        started_at=datetime(2026, 11, 2, 14, 0),
        completed_at=datetime(2026, 11, 2, 14, 0, 2),
        duration_ms=2000,
        status="completed",
    )

    class FakeRepository:
        def check_database(self):
            pass

        def system_overview_data(self, seven_days_ago, twenty_four_hours_ago):
            assert (twenty_four_hours_ago - seven_days_ago).days == 6
            return {
                "schema_revision": "0005_system_overview_metrics",
                "active_rules": 18,
                "last_run": last_run,
                "records": {"customers": {"total": 10}},
                "active_users": 4,
                "total_users": 5,
                "audit_counts": {
                    "failed_logins_last_24h": 1,
                    "access_denied_last_24h": 2,
                },
            }

    monkeypatch.setenv("ENABLE_DEMO_ENDPOINTS", "true")
    overview = AnalysisService(FakeRepository()).system_overview()

    assert overview["health"]["api"] == "ok"
    assert overview["health"]["database"] == "connected"
    assert overview["health"]["schema_revision"] == "0005_system_overview_metrics"
    assert overview["rules"]["active"] == 18
    assert overview["rules"]["last_run_duration_ms"] == 2000
    assert overview["records"]["customers"]["total"] == 10
    assert overview["security"] == {
        "session_ttl_seconds": 1800,
        "demo_endpoint_enabled": True,
        "active_users": 4,
        "total_users": 5,
        "csv_max_bytes": 5 * 1024 * 1024,
        "csv_max_rows": 5000,
        "failed_logins_last_24h": 1,
        "access_denied_last_24h": 2,
    }
