from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import (
    Account,
    AuditLog,
    Customer,
    Transaction,
    UploadBatch,
    UploadRowError,
)
from backend.repositories.user_repository import SqlAlchemyUserRepository


class SqlAlchemyUploadRepository:
    _models: dict[str, type[Any]] = {
        "customer": Customer,
        "account": Account,
        "transaction": Transaction,
    }
    _unique_columns = {
        "customer": "customer_no",
        "account": "account_no",
        "transaction": "transaction_no",
    }

    def __init__(self, session: Session) -> None:
        self._session = session
        self._users = SqlAlchemyUserRepository(session)

    def system_user_id(self) -> int:
        return self._users.get_or_create_system_user_id()

    def get_customer(self, customer_no: str) -> Customer | None:
        return self._session.scalar(
            select(Customer).where(Customer.customer_no == customer_no)
        )

    def get_account(self, account_no: str) -> Account | None:
        return self._session.scalar(
            select(Account).where(Account.account_no == account_no)
        )

    def exists(self, entity: str, unique_value: str) -> bool:
        model = self._models[entity]
        unique_column = self._unique_columns[entity]
        return (
            self._session.scalar(
                select(model).where(
                    getattr(model, unique_column) == unique_value
                )
            )
            is not None
        )

    def create_batch(
        self,
        *,
        actor_id: int,
        entity: str,
        file_name: str,
        total_rows: int,
    ) -> UploadBatch:
        batch = UploadBatch(
            uploaded_by=actor_id,
            entity_type=entity,
            file_name=file_name,
            total_rows=total_rows,
            accepted_rows=0,
            rejected_rows=0,
        )
        self._session.add(batch)
        self._session.flush()
        return batch

    def persist_upload(
        self,
        batch: UploadBatch,
        accepted: list[Any],
        errors: list[UploadRowError],
        actor_id: int,
        entity: str,
    ) -> None:
        batch.accepted_rows = len(accepted)
        batch.rejected_rows = len(errors)
        self._session.add_all(accepted)
        self._session.add_all(errors)
        self._session.add(
            AuditLog(
                actor_id=actor_id,
                action="csv.uploaded",
                entity_type=entity,
                entity_id=str(batch.batch_id),
                details={
                    "total_rows": batch.total_rows,
                    "accepted_rows": batch.accepted_rows,
                    "rejected_rows": batch.rejected_rows,
                },
            )
        )
        self._session.commit()

    def get_batch(self, batch_id: int) -> UploadBatch | None:
        return self._session.scalar(
            select(UploadBatch)
            .where(UploadBatch.batch_id == batch_id)
            .options(selectinload(UploadBatch.errors))
        )
