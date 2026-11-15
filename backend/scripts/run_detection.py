"""Run every active rule over all data once, as the system (no user).

The same run the API's daily scheduler makes (backend/scheduler.py), for use
from cron, an ECS scheduled task or by hand. Writes to the database in
DATABASE_URL and records a `detection.auto_run` audit event.

Run:  python -m backend.scripts.run_detection
"""

from dotenv import load_dotenv

from backend.scheduler import run_scheduled_detection


def main() -> None:
    load_dotenv()
    created = run_scheduled_detection(trigger="manual-script")
    print(f"Detection run finished: {created} new alerts.")


if __name__ == "__main__":
    main()
