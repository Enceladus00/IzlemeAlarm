from datetime import date, datetime, time, timedelta
from typing import Any

from backend.repositories.analysis_repository import SqlAlchemyAnalysisRepository


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
