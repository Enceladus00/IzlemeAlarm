from datetime import datetime, time, timedelta

import pytest

from backend import scheduler
from backend.scheduler import DetectionScheduler, next_run_after, parse_schedule_time


@pytest.mark.parametrize("value", [None, "", "   "])
def test_unset_schedule_means_off(value):
    assert parse_schedule_time(value) is None


def test_parses_hours_and_minutes():
    assert parse_schedule_time(" 02:30 ") == time(2, 30)


@pytest.mark.parametrize("value", ["2", "25:00", "02:60", "aa:bb", "02:30:00"])
def test_rejects_malformed_times(value):
    with pytest.raises(RuntimeError, match="DETECTION_SCHEDULE_TIME"):
        parse_schedule_time(value)


def test_next_run_is_today_when_the_time_is_still_ahead():
    assert next_run_after(datetime(2026, 11, 15, 1, 0), time(2, 0)) == datetime(2026, 11, 15, 2, 0)


@pytest.mark.parametrize("now", [datetime(2026, 11, 15, 2, 0), datetime(2026, 11, 15, 23, 59)])
def test_next_run_is_tomorrow_once_the_time_has_come(now):
    assert next_run_after(now, time(2, 0)) == datetime(2026, 11, 16, 2, 0)


def test_no_scheduler_without_the_setting(monkeypatch):
    monkeypatch.delenv("DETECTION_SCHEDULE_TIME", raising=False)
    assert scheduler.start_scheduler_from_env() is None


def test_scheduler_runs_when_due_and_stops(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "run_scheduled_detection", lambda: calls.append(1) or 0)
    # Due immediately on the first loop, then a day later: exactly one run.
    monkeypatch.setattr(
        scheduler,
        "next_run_after",
        lambda now, at: now if not calls else now + timedelta(days=1),
    )
    job = DetectionScheduler(time(2, 0))
    job.start()
    for _ in range(100):
        if calls:
            break
        job._stop.wait(0.01)
    job.stop()
    assert calls == [1]
    assert not job._thread.is_alive()


def test_a_failed_run_does_not_end_the_schedule(monkeypatch):
    attempts = []

    def failing():
        attempts.append(1)
        raise RuntimeError("database down")

    monkeypatch.setattr(scheduler, "run_scheduled_detection", failing)
    monkeypatch.setattr(
        scheduler,
        "next_run_after",
        lambda now, at: now if len(attempts) < 2 else now + timedelta(days=1),
    )
    job = DetectionScheduler(time(2, 0))
    job.start()
    for _ in range(100):
        if len(attempts) >= 2:
            break
        job._stop.wait(0.01)
    job.stop()
    assert len(attempts) == 2
