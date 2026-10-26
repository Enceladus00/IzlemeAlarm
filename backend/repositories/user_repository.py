from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from backend.models import AppRole, AppUser, AuditLog


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_users(self) -> list[AppUser]:
        return list(
            self._session.scalars(
                select(AppUser)
                .options(joinedload(AppUser.role))
                .order_by(AppUser.username)
            ).unique()
        )

    def get_user(self, user_id: int) -> AppUser | None:
        return self._session.scalar(
            select(AppUser)
            .where(AppUser.user_id == user_id)
            .options(joinedload(AppUser.role))
        )

    def get_role(self, role_code: str) -> AppRole | None:
        return self._session.scalar(
            select(AppRole).where(AppRole.role_code == role_code)
        )

    def list_active_roles(self) -> list[AppRole]:
        return list(
            self._session.scalars(
                select(AppRole)
                .where(AppRole.is_active)
                .order_by(AppRole.role_code)
            )
        )

    def username_exists(self, username: str) -> bool:
        return self._session.scalar(
            select(AppUser.user_id).where(AppUser.username == username)
        ) is not None

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: AppRole,
        actor_id: int,
    ) -> AppUser:
        try:
            user = AppUser(
                username=username,
                password_hash=password_hash,
                role=role,
            )
            self._session.add(user)
            self._session.flush()
            self._session.add(
                AuditLog(
                    actor_id=actor_id,
                    action="USER_CREATED",
                    entity_type="app_user",
                    entity_id=str(user.user_id),
                    details={"username": username, "role_code": role.role_code},
                )
            )
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return user

    def save_user(
        self,
        user: AppUser,
        *,
        actor_id: int,
        role_changed: bool,
        is_active_changed: bool,
    ) -> AppUser:
        try:
            self._session.add(
                AuditLog(
                    actor_id=actor_id,
                    action="USER_UPDATED",
                    entity_type="app_user",
                    entity_id=str(user.user_id),
                    details={
                        "role_code": user.role.role_code,
                        "is_active": user.is_active,
                        "role_changed": role_changed,
                        "is_active_changed": is_active_changed,
                    },
                )
            )
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return user
