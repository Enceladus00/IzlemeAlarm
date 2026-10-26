import os
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt


JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 30
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(
    b"invalid-login-placeholder",
    bcrypt.gensalt(),
)


def get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is required.")
    return secret


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Passwords must not exceed 72 UTF-8 bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Passwords must not exceed 72 UTF-8 bytes.")
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def perform_dummy_password_check(password: str) -> None:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        encoded = b"\x00" * 72
    bcrypt.checkpw(encoded, _DUMMY_PASSWORD_HASH)


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_MINUTES
    )
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at},
        get_jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> int:
    claims: dict[str, Any] = jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.isdecimal():
        raise jwt.InvalidTokenError("Invalid token subject.")
    return int(subject)
