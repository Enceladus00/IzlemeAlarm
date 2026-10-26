from dataclasses import dataclass

import jwt

from backend.models import AppUser
from backend.repositories.audit_repository import AuditLogRepository
from backend.repositories.auth_repository import SqlAlchemyAuthRepository
from backend.security import (
    create_access_token,
    decode_access_token,
    perform_dummy_password_check,
    verify_password,
)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: int
    username: str
    role_code: str
    permissions: frozenset[str]


class AuthService:
    def __init__(
        self,
        repository: SqlAlchemyAuthRepository,
        audit_repository: AuditLogRepository,
    ) -> None:
        self._repository = repository
        self._audit = audit_repository

    def login(self, username: str, password: str) -> str | None:
        user = self._repository.get_by_username(username)
        password_matches = False
        if user is None:
            perform_dummy_password_check(password)
        else:
            try:
                password_matches = verify_password(password, user.password_hash)
            except ValueError:
                perform_dummy_password_check(password)

        if (
            user is None
            or not password_matches
            or not user.is_active
            or not user.role.is_active
        ):
            self._audit.write_event(
                action="LOGIN_FAILED",
                entity_type="auth",
                actor_id=None,
                details={"username": username},
            )
            return None

        self._audit.write_event(
            action="LOGIN_SUCCESS",
            entity_type="auth",
            entity_id=str(user.user_id),
            actor_id=user.user_id,
            details={"username": username},
        )
        return create_access_token(user.user_id)

    def user_from_token(self, token: str) -> AuthenticatedUser:
        user_id = decode_access_token(token)
        user = self._repository.get_by_id(user_id)
        if user is None or not user.is_active or not user.role.is_active:
            raise jwt.InvalidTokenError("Inactive or missing user.")
        return self._authenticated_user(user)

    @staticmethod
    def _authenticated_user(user: AppUser) -> AuthenticatedUser:
        return AuthenticatedUser(
            user_id=user.user_id,
            username=user.username,
            role_code=user.role.role_code,
            permissions=frozenset(
                permission.code for permission in user.role.permissions
            ),
        )
