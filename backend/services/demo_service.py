from datetime import datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.demo import DEMO_RULE_OVERRIDES, seed_demo_data
from backend.services.detection_service import DetectionService


class DemoService:
    def __init__(self, session: Session, detection_service: DetectionService) -> None:
        self._session = session
        self._detection_service = detection_service

    def seed(self, actor_id: int) -> dict[str, Any]:
        try:
            as_of = datetime.now()
            counts = seed_demo_data(self._session, as_of=as_of)
            created = self._detection_service.evaluate(
                actor_id=actor_id,
                automatic=True,
                as_of=as_of,
                customer_ids=set(counts["demo_customer_ids"]),
                rule_overrides=DEMO_RULE_OVERRIDES,
            )
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return {
            **counts,
            "created_alerts": created,
            "demo_only_parameters": True,
            "scenarios": [
                "R01: repeated near-limit transfers -> alert",
                "R02: one limit-sized transfer -> INFO signal only",
                "R03: three below-limit cash deposits to one account -> alert",
            ],
        }
