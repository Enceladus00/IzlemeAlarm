"""Scheduled detection run: the rules evaluated once a day, without a user.

Off unless DETECTION_SCHEDULE_TIME is set to a local time "HH:MM" (the
process's clock; a container usually runs on UTC). The API then starts one
background thread that sleeps until that time, runs every active rule over all
data, and repeats the next day. A run missed while the API was down is not
caught up.

Like the rate limits, this assumes one API task. With several tasks each would
run the rules; the advisory lock and alert deduplication prevent duplicate
alerts, so that is wasteful but not harmful.

The same run can be started from outside with
`python -m backend.scripts.run_detection`.
"""

import logging
import os
import threading
from datetime import datetime, time, timedelta

from backend.database import create_independent_session
from backend.repositories.detection_repository import SqlAlchemyDetectionRepository
from backend.services.detection_service import DetectionService


logger = logging.getLogger(__name__)

SCHEDULE_ENV = "DETECTION_SCHEDULE_TIME"
SCHEDULED_TRIGGER = "scheduled"


def parse_schedule_time(value: str | None) -> time | None:
    """'HH:MM' -> time; empty or unset -> None (scheduler off)."""
    if value is None or not value.strip():
        return None
    try:
        hours, minutes = value.strip().split(":")
        return time(int(hours), int(minutes))
    except ValueError as exc:
        raise RuntimeError(f"{SCHEDULE_ENV} must be HH:MM, got {value!r}.") from exc


def next_run_after(now: datetime, at: time) -> datetime:
    candidate = datetime.combine(now.date(), at)
    return candidate if candidate > now else candidate + timedelta(days=1)


def run_scheduled_detection(trigger: str = SCHEDULED_TRIGGER) -> int:
    """Evaluate every active rule over all data as the system. Returns new alerts."""
    with create_independent_session() as session:
        service = DetectionService(SqlAlchemyDetectionRepository(session))
        return service.evaluate(automatic=True, trigger=trigger)


class DetectionScheduler:
    def __init__(self, at: time) -> None:
        self._at = at
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="detection-scheduler", daemon=True
        )

    def start(self) -> None:
        logger.info("Scheduled detection enabled: every day at %s", self._at.strftime("%H:%M"))
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while True:
            due = next_run_after(datetime.now(), self._at)
            if self._stop.wait((due - datetime.now()).total_seconds()):
                return
            try:
                created = run_scheduled_detection()
                logger.info("Scheduled detection run finished: %s new alerts", created)
            except Exception:  # keep the schedule alive; the next day tries again
                logger.exception("Scheduled detection run failed")


def start_scheduler_from_env() -> DetectionScheduler | None:
    at = parse_schedule_time(os.getenv(SCHEDULE_ENV))
    if at is None:
        return None
    scheduler = DetectionScheduler(at)
    scheduler.start()
    return scheduler
