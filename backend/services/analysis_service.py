import os
from datetime import date, datetime, time, timedelta
from time import perf_counter
from typing import Any

from backend.repositories.analysis_repository import SqlAlchemyAnalysisRepository
from backend.security import ACCESS_TOKEN_MINUTES
from backend.services.upload_service import MAX_UPLOAD_BYTES, MAX_UPLOAD_ROWS


class AnalysisService:
    def __init__(self, repository: SqlAlchemyAnalysisRepository) -> None:
        self._repository = repository

    def check_health(self) -> dict[str, str]:
        self._repository.check_database()
        return {"status": "ok", "database": "connected"}

    def dashboard_summary(self) -> dict[str, Any]:
        today = date.today()
        first_trend_day = today - timedelta(days=29)
        data = self._repository.dashboard_data(
            datetime.combine(first_trend_day, time.min),
            datetime.combine(today + timedelta(days=1), time.min),
        )
        alert_dates = {
            day: int(count) for day, count in data["alert_trends"]
        }
        suspicious_dates = {
            day: int(count) for day, count in data["suspicious_trends"]
        }
        return {
            **{
                key: int(value or 0)
                for key, value in data["totals"].items()
            },
            "by_status": {
                key: int(value) for key, value in data["statuses"]
            },
            "by_severity": {
                key: int(value) for key, value in data["severities"]
            },
            "by_rule": {
                key: int(value) for key, value in data["rules"]
            },
            "trends": [
                {
                    "date": day,
                    "alerts": alert_dates.get(day, 0),
                    "suspicious_transactions": suspicious_dates.get(day, 0),
                }
                for day in (
                    first_trend_day + timedelta(days=offset)
                    for offset in range(30)
                )
            ],
        }

    def system_overview(self) -> dict[str, Any]:
        now = datetime.now()
        database_started = perf_counter()
        self._repository.check_database()
        database_latency_ms = round((perf_counter() - database_started) * 1000, 1)
        data = self._repository.system_overview_data(
            now - timedelta(days=7),
            now - timedelta(hours=24),
        )
        last_run = data["last_run"]
        last_run_at = (
            (last_run.completed_at or last_run.started_at) if last_run else None
        )
        return {
            "health": {
                "api": "ok",
                "database": "connected",
                "database_latency_ms": database_latency_ms,
                "schema_revision": data["schema_revision"],
            },
            "rules": {
                "active": data["active_rules"],
                "last_run_at": last_run_at,
                "last_run_status": last_run.status if last_run else None,
                "last_run_duration_ms": last_run.duration_ms if last_run else None,
            },
            "records": data["records"],
            "security": {
                "session_ttl_seconds": ACCESS_TOKEN_MINUTES * 60,
                "demo_endpoint_enabled": (
                    os.getenv("ENABLE_DEMO_ENDPOINTS", "").lower() == "true"
                ),
                "active_users": data["active_users"],
                "total_users": data["total_users"],
                "csv_max_bytes": MAX_UPLOAD_BYTES,
                "csv_max_rows": MAX_UPLOAD_ROWS,
                **data["audit_counts"],
            },
        }
