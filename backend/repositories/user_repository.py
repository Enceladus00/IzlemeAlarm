from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.demo import SYSTEM_USERNAME
from backend.models import AppUser


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create_system_user_id(self) -> int:
        user = self._session.scalar(
            select(AppUser).where(AppUser.username == SYSTEM_USERNAME)
        )
        if user is None:
            user = AppUser(
                username=SYSTEM_USERNAME,
                password_hash="not-a-login-account",
                role="analyst",
            )
            self._session.add(user)
            self._session.flush()
        return user.user_id
