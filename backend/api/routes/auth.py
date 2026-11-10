from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from backend.api.dependencies import get_auth_service, get_current_user, too_many_requests
from backend.rate_limit import (
    begin_login_attempt,
    client_address,
    login_not_checked,
    login_succeeded,
    password_checks,
)
from backend.security import ACCESS_TOKEN_MINUTES
from backend.services.auth_service import AuthenticatedUser, AuthService


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str | int]:
    address = client_address(request)
    block = begin_login_attempt(address, form.username)
    if block is not None:
        if block.first_rejection:
            service.record_login_blocked(block.scope, address)
        raise too_many_requests(block.retry_after)
    if not password_checks.acquire(blocking=False):
        login_not_checked(address, form.username)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Too many sign-ins in progress. Please try again shortly.",
            headers={"Retry-After": "5"},
        )
    try:
        token = service.login(form.username, form.password)
    except Exception:
        login_not_checked(address, form.username)
        raise
    finally:
        password_checks.release()
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_succeeded(address, form.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
    }


@router.get("/me")
def get_me(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, object]:
    return {
        "username": user.username,
        "role_code": user.role_code,
        "permissions": sorted(user.permissions),
    }
