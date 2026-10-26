from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.api.dependencies import get_user_service, require_permission
from backend.api_schemas import UserCreate, UserUpdate
from backend.services.auth_service import AuthenticatedUser
from backend.services.user_service import (
    DuplicateUsername,
    InvalidUserInput,
    UserNotFound,
    UserRoleNotFound,
    UserService,
)


router = APIRouter(tags=["users"])


@router.get("/users")
def list_users(
    _actor: AuthenticatedUser = Depends(require_permission("user:manage")),
    service: UserService = Depends(get_user_service),
) -> list[dict[str, Any]]:
    return service.list_users()


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    request: UserCreate,
    actor: AuthenticatedUser = Depends(require_permission("user:manage")),
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    try:
        return service.create_user(
            username=request.username,
            password=request.password,
            role_code=request.role_code,
            actor_id=actor.user_id,
        )
    except DuplicateUsername as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UserRoleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidUserInput as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="User could not be created.") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not create user.") from exc


@router.get("/users/roles")
def list_roles(
    _actor: AuthenticatedUser = Depends(require_permission("user:manage")),
    service: UserService = Depends(get_user_service),
) -> list[dict[str, str]]:
    return service.list_roles()


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    request: UserUpdate,
    actor: AuthenticatedUser = Depends(require_permission("user:manage")),
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    try:
        return service.update_user(
            user_id,
            role_code=request.role_code,
            is_active=request.is_active,
            actor_id=actor.user_id,
        )
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UserRoleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidUserInput as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not update user.") from exc
