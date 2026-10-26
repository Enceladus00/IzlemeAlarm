from typing import Any

from backend.models import AppUser
from backend.repositories.user_repository import SqlAlchemyUserRepository
from backend.security import hash_password


class UserNotFound(LookupError):
    pass


class UserRoleNotFound(LookupError):
    pass


class DuplicateUsername(ValueError):
    pass


class InvalidUserInput(ValueError):
    pass


class UserService:
    def __init__(self, repository: SqlAlchemyUserRepository) -> None:
        self._repository = repository

    def list_users(self) -> list[dict[str, Any]]:
        return [self._user_view(user) for user in self._repository.list_users()]

    def list_roles(self) -> list[dict[str, str]]:
        return [
            {"role_code": role.role_code, "name": role.name}
            for role in self._repository.list_active_roles()
        ]

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role_code: str,
        actor_id: int,
    ) -> dict[str, Any]:
        normalized_username = username.strip()
        if not normalized_username or len(normalized_username) > 50:
            raise InvalidUserInput("Username must contain 1 to 50 characters.")
        try:
            password_hash = hash_password(password)
        except ValueError as exc:
            raise InvalidUserInput(str(exc)) from exc
        role = self._repository.get_role(role_code)
        if role is None or not role.is_active:
            raise UserRoleNotFound("Role not found.")
        if self._repository.username_exists(normalized_username):
            raise DuplicateUsername("Username already exists.")
        user = self._repository.create_user(
            username=normalized_username,
            password_hash=password_hash,
            role=role,
            actor_id=actor_id,
        )
        return self._user_view(user)

    def update_user(
        self,
        user_id: int,
        *,
        role_code: str | None,
        is_active: bool | None,
        actor_id: int,
    ) -> dict[str, Any]:
        if role_code is None and is_active is None:
            raise InvalidUserInput("Provide a role_code or is_active update.")
        user = self._repository.get_user(user_id)
        if user is None:
            raise UserNotFound("User not found.")
        role_changed = role_code is not None and user.role.role_code != role_code
        active_changed = is_active is not None and user.is_active != is_active
        if role_code is not None:
            role = self._repository.get_role(role_code)
            if role is None or not role.is_active:
                raise UserRoleNotFound("Role not found.")
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        user = self._repository.save_user(
            user,
            actor_id=actor_id,
            role_changed=role_changed,
            is_active_changed=active_changed,
        )
        return self._user_view(user)

    @staticmethod
    def _user_view(user: AppUser) -> dict[str, Any]:
        return {
            "user_id": user.user_id,
            "username": user.username,
            "role_code": user.role.role_code,
            "is_active": user.is_active,
            "created_at": user.created_at,
        }
