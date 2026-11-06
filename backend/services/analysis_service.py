import os
from pathlib import Path
from datetime import date, datetime, time, timedelta
from time import perf_counter
from typing import Any

from backend.repositories.analysis_repository import SqlAlchemyAnalysisRepository
from backend.security import ACCESS_TOKEN_MINUTES
from backend.services.upload_service import MAX_UPLOAD_BYTES, MAX_UPLOAD_ROWS


def schema_head() -> str | None:
    """The newest Alembic revision known to this code (compared with the database's)."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        root = Path(__file__).resolve().parents[2]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "alembic"))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:  # pragma: no cover - missing alembic files must not break the page
        return None


class AnalysisService:
    def __init__(self, repository: SqlAlchemyAnalysisRepository) -> None:
        self._repository = repository

    def check_health(self) -> dict[str, str]:
        self._repository.check_database()
        return {"status": "ok", "database": "connected"}

    def dashboard_summary(self, days: int = 30) -> dict[str, Any]:
        today = date.today()
        first_trend_day = today - timedelta(days=days - 1)
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
            "days": days,
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
                    for offset in range(days)
                )
            ],
        }

    def funnel(self, days: int) -> dict[str, Any]:
        since = datetime.combine(date.today() - timedelta(days=days - 1), time.min)
        row = self._repository.funnel_data(since)
        average = row.pop("avg_decision_days", None)
        result = {key: int(value or 0) for key, value in row.items()}
        decided_escalations = result["confirmed"] + result["escalated_closed"]
        return {
            "days": days,
            "created": result["created"],
            "open": result["open"],
            "confirmed": result["confirmed"],
            # E10 KPIs; null when there is nothing to divide by.
            "escalation_rate": round(result["escalated"] / result["created"], 3)
            if result["created"]
            else None,
            "confirmed_rate": round(result["confirmed"] / decided_escalations, 3)
            if decided_escalations
            else None,
            "avg_decision_days": round(float(average), 1) if average is not None else None,
            "analyst_closed": result["analyst_closed"],
            "analyst_open": result["analyst_open"],
            "escalated": result["escalated"],
            "escalation_outcome": {
                "confirmed": result["confirmed"],
                "closed": result["escalated_closed"],
                "returned": result["returned"],
                "pending": result["pending"],
            },
        }

    def rule_performance(self, days: int) -> list[dict[str, Any]]:
        since = datetime.combine(date.today() - timedelta(days=days - 1), time.min)
        rows = []
        for row in self._repository.rule_performance_data(since):
            confirmed = int(row["confirmed"] or 0)
            closed = int(row["closed"] or 0)
            decided = confirmed + closed
            thresholds = row["thresholds"] or {}
            rows.append(
                {
                    "rule_code": row["rule_code"],
                    "name": row["name"],
                    "is_active": row["is_active"],
                    "evaluated": int(row["evaluated"] or 0),
                    "alerts": int(row["alerts"] or 0),
                    "avg_alert_score": row["avg_alert_score"],
                    "confirmed": confirmed,
                    "closed": closed,
                    "hit_rate": round(confirmed / decided, 3) if decided else None,
                    "provisional": any(
                        isinstance(item, dict) and item.get("status") == "PROVISIONAL"
                        for item in thresholds.values()
                    ),
                }
            )
        return rows

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
                "schema_head": schema_head(),
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
