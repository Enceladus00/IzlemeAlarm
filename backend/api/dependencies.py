import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.repositories.audit_repository import AuditLogRepository
from backend.repositories.auth_repository import SqlAlchemyAuthRepository
from backend.repositories.alert_repository import SqlAlchemyAlertRepository
from backend.repositories.audit_query_repository import SqlAlchemyAuditQueryRepository
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
from backend.services.auth_service import AuthenticatedUser, AuthService
from backend.services.audit_service import AuditService
from backend.repositories.user_repository import SqlAlchemyUserRepository
from backend.services.user_service import UserService


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False,
)


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(SqlAlchemyAuthRepository(db), AuditLogRepository())


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(SqlAlchemyUserRepository(db))


def get_audit_service(db: Session = Depends(get_db)) -> AuditService:
    return AuditService(SqlAlchemyAuditQueryRepository(db))


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUser:
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return service.user_from_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_permission(permission_code: str):
    def permission_dependency(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if permission_code not in user.permissions:
            AuditLogRepository().write_event(
                action="ACCESS_DENIED",
                entity_type="permission",
                entity_id=permission_code,
                actor_id=user.user_id,
                details={"username": user.username},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission_code}.",
            )
        return user

    return permission_dependency


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
