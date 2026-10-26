from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from backend.api.dependencies import get_auth_service, get_current_user
from backend.services.auth_service import AuthenticatedUser, AuthService


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    token = service.login(form.username, form.password)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def get_me(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, object]:
    return {
        "username": user.username,
        "role_code": user.role_code,
        "permissions": sorted(user.permissions),
    }
