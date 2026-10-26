import getpass
import os

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.database import create_independent_session
from backend.models import AppRole, AppUser
from backend.security import hash_password


def main() -> None:
    load_dotenv()
    username = os.getenv("ADMIN_USERNAME") or input("Admin username: ").strip()
    password = os.getenv("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    if not username or len(username) > 50:
        raise ValueError("Username must contain 1 to 50 characters.")
    if not password:
        raise ValueError("Password must not be empty.")

    session = create_independent_session()
    try:
        if session.scalar(select(AppUser.user_id).where(AppUser.username == username)):
            raise ValueError(f"User {username!r} already exists.")
        admin_role = session.scalar(
            select(AppRole).where(AppRole.role_code == "admin")
        )
        if admin_role is None:
            raise RuntimeError("Apply the RBAC migration before creating an admin.")
        session.add(
            AppUser(
                username=username,
                password_hash=hash_password(password),
                role=admin_role,
            )
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()
    print(f"Created admin user {username!r}.")


if __name__ == "__main__":
    main()
