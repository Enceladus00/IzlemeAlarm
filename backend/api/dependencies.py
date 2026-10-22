from fastapi import Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.repositories.alert_repository import SqlAlchemyAlertRepository
from backend.repositories.analysis_repository import SqlAlchemyAnalysisRepository
from backend.repositories.detection_repository import SqlAlchemyDetectionRepository
from backend.repositories.transaction_repository import SqlAlchemyTransactionRepository
from backend.repositories.rule_repository import SqlAlchemyRuleRepository
from backend.services.detection_service import DetectionService
from backend.services.alert_service import AlertService
from backend.services.analysis_service import AnalysisService
from backend.services.transaction_service import TransactionService
from backend.services.rule_service import RuleService
from backend.services.demo_service import DemoService
from backend.services.upload_service import UploadService


def get_transaction_service(
    db: Session = Depends(get_db),
) -> TransactionService:
    return TransactionService(SqlAlchemyTransactionRepository(db))


def get_alert_service(db: Session = Depends(get_db)) -> AlertService:
    return AlertService(SqlAlchemyAlertRepository(db))


def get_analysis_service(db: Session = Depends(get_db)) -> AnalysisService:
    return AnalysisService(SqlAlchemyAnalysisRepository(db))


def get_rule_service(db: Session = Depends(get_db)) -> RuleService:
    return RuleService(SqlAlchemyRuleRepository(db))


def get_detection_service(db: Session = Depends(get_db)) -> DetectionService:
    return DetectionService(SqlAlchemyDetectionRepository(db))


def get_demo_service(db: Session = Depends(get_db)) -> DemoService:
    detection_service = DetectionService(SqlAlchemyDetectionRepository(db))
    return DemoService(db, detection_service)


def get_upload_service(db: Session = Depends(get_db)) -> UploadService:
    detection_service = DetectionService(SqlAlchemyDetectionRepository(db))
    return UploadService(db, detection_service)
