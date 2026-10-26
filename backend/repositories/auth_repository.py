from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import AppRole, AppUser


class SqlAlchemyAuthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _user_query():
        return select(AppUser).options(
            selectinload(AppUser.role).selectinload(AppRole.permissions)
        )

    def get_by_username(self, username: str) -> AppUser | None:
        return self._session.scalar(
            self._user_query().where(AppUser.username == username)
        )

    def get_by_id(self, user_id: int) -> AppUser | None:
        return self._session.scalar(
            self._user_query().where(AppUser.user_id == user_id)
        )
