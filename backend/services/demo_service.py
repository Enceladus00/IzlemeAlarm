from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.demo import seed_demo_data
from backend.services.detection_service import DetectionService


class DemoService:
    def __init__(self, session: Session, detection_service: DetectionService) -> None:
        self._session = session
        self._detection_service = detection_service

    def seed(self, actor_id: int) -> dict[str, Any]:
        try:
            counts = seed_demo_data(self._session)
            created = self._detection_service.evaluate(
                actor_id=actor_id,
                automatic=True,
            )
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return {**counts, "created_alerts": created}
