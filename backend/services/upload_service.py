import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models import (
    Account,
    Customer,
    Transaction,
    UploadRowError,
)
from backend.repositories.upload_repository import SqlAlchemyUploadRepository
from backend.services.detection_service import DetectionService

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_ROWS = 5000
CHANNELS = {"atm", "mobile", "internet", "branch"}
ENTITY_HEADERS = {
    "customer": {"customer_no", "full_name", "customer_type", "occupation", "monthly_income", "risk_level"},
    "account": {"account_no", "customer_no", "currency", "account_type", "opened_at"},
    "transaction": {"transaction_no", "sender_account_no", "receiver_account_no", "amount", "currency", "tx_time", "channel", "country_code"},
}

def _text_field(
    row: dict[str, str], name: str, maximum: int, *, required: bool = False
) -> str | None:
    value = row.get(name, "").strip()
    if required and not value:
        raise ValueError(f"{name} is required")
    if value and len(value) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")
    return value or None

def _required_text(row: dict[str, str], name: str, maximum: int) -> str:
    value = _text_field(row, name, maximum, required=True)
    if value is None:
        raise ValueError(f"{name} is required")
    return value

def _money_field(
    value: str, name: str, *, allow_zero: bool = False
) -> Decimal:
    amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError(f"{name} must be a finite number")
    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError(f"{name} must be positive")
    if amount.as_tuple().exponent < -2:
        raise ValueError(f"{name} must have at most two decimal places")
    if amount >= Decimal("10000000000000000"):
        raise ValueError(f"{name} is too large")
    return amount

def _parse_row(
    entity: str,
    row: dict[str, str],
    repository: SqlAlchemyUploadRepository,
) -> Any:
    if entity == "customer":
        income = (
            _money_field(row["monthly_income"], "monthly_income", allow_zero=True)
            if row.get("monthly_income")
            else None
        )
        return Customer(
            customer_no=_required_text(row, "customer_no", 20),
            full_name=_required_text(row, "full_name", 100),
            customer_type=_text_field(row, "customer_type", 10),
            occupation=_text_field(row, "occupation", 50),
            monthly_income=income,
            risk_level=_text_field(row, "risk_level", 6),
        )
    if entity == "account":
        customer_no = row.get("customer_no", "").strip()
        customer = repository.get_customer(customer_no)
        if customer is None:
            raise ValueError(f"Unknown customer_no: {customer_no}")
        account_no = _required_text(row, "account_no", 34)
        currency = _required_text(row, "currency", 3).upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("currency must be a three-letter code")
        opened = date.fromisoformat(row["opened_at"]) if row.get("opened_at") else None
        return Account(
            account_no=account_no,
            customer_id=customer.customer_id,
            currency=currency,
            account_type=_text_field(row, "account_type", 10),
            opened_at=opened,
        )
    sender_no = row.get("sender_account_no", "").strip()
    receiver_no = row.get("receiver_account_no", "").strip()
    sender = repository.get_account(sender_no)
    receiver = repository.get_account(receiver_no)
    if sender is None or receiver is None:
        raise ValueError("sender_account_no and receiver_account_no must exist")
    amount = _money_field(row["amount"], "amount")
    channel = row["channel"].lower()
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of: {', '.join(sorted(CHANNELS))}")
    country = row["country_code"].upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("country_code must be a two-letter ISO code")
    currency = row["currency"].upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("currency must be a three-letter code")
    if sender.currency != currency or receiver.currency != currency:
        raise ValueError("transaction currency must match both account currencies")
    timestamp = datetime.fromisoformat(row["tx_time"])
    if timestamp.tzinfo is not None:
        raise ValueError("tx_time must not include a timezone")
    return Transaction(
        transaction_no=_required_text(row, "transaction_no", 30),
        sender_account_id=sender.account_id,
        receiver_account_id=receiver.account_id,
        amount=amount,
        currency=currency,
        tx_time=timestamp,
        channel=channel,
        country_code=country,
    )

async def upload_csv(
    entity: str,
    file: UploadFile,
    db: Session,
    detection_service: DetectionService,
    actor_id: int,
) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Upload a .csv file.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV exceeds the 5 MB limit.")
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must use UTF-8 encoding.") from exc
    try:
        reader = csv.DictReader(io.StringIO(text_content), strict=True)
        headers = set(reader.fieldnames or [])
        rows = list(reader)
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail=f"Malformed CSV: {exc}") from exc
    missing = ENTITY_HEADERS[entity] - headers
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing CSV columns: {', '.join(sorted(missing))}",
        )
    if len(rows) > MAX_UPLOAD_ROWS:
        raise HTTPException(status_code=413, detail="CSV exceeds the 5000-row limit.")

    repository = SqlAlchemyUploadRepository(db)
    batch = repository.create_batch(
        actor_id=actor_id,
        entity=entity,
        file_name=Path(file.filename).name,
        total_rows=len(rows),
    )
    errors: list[UploadRowError] = []
    accepted: list[Any] = []
    seen: set[str] = set()
    unique_column = {
        "customer": "customer_no",
        "account": "account_no",
        "transaction": "transaction_no",
    }[entity]
    for row_number, row in enumerate(rows, 2):
        try:
            if None in row:
                raise ValueError("row has more fields than the CSV header")
            unique_value = (row.get(unique_column) or "").strip()
            if not unique_value:
                raise ValueError(f"{unique_column} is required")
            if unique_value in seen:
                raise ValueError(f"Duplicate {unique_column} in this file")
            seen.add(unique_value)
            record = _parse_row(entity, row, repository)
            if repository.exists(entity, unique_value):
                raise ValueError(f"{unique_column} already exists")
            accepted.append(record)
        except (ValueError, InvalidOperation, KeyError) as exc:
            errors.append(
                UploadRowError(
                    batch_id=batch.batch_id,
                    row_number=row_number,
                    reason=str(exc),
                    row_data={
                        key: value for key, value in row.items()
                        if isinstance(key, str) and value is not None
                    },
                )
            )
    try:
        repository.persist_upload(batch, accepted, errors, actor_id, entity)
        if entity == "transaction" and accepted:
            detection_service.evaluate(
                actor_id=actor_id,
                automatic=True,
            )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail="CSV records violate database constraints.") from exc
    return {
        "batch_id": batch.batch_id,
        "entity_type": entity,
        "total_rows": batch.total_rows,
        "accepted_rows": batch.accepted_rows,
        "rejected_rows": batch.rejected_rows,
        "errors": [
            {"row_number": error.row_number, "reason": error.reason, "row_data": error.row_data}
            for error in errors
        ],
    }

def get_upload(batch_id: int, db: Session) -> dict[str, Any]:
    batch = SqlAlchemyUploadRepository(db).get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Upload batch not found.")
    return {
        "batch_id": batch.batch_id,
        "entity_type": batch.entity_type,
        "file_name": batch.file_name,
        "total_rows": batch.total_rows,
        "accepted_rows": batch.accepted_rows,
        "rejected_rows": batch.rejected_rows,
        "uploaded_at": batch.uploaded_at,
        "errors": [
            {
                "row_number": error.row_number,
                "reason": error.reason,
                "row_data": error.row_data,
            }
            for error in batch.errors
        ],
    }


class UploadService:
    def __init__(
        self,
        session: Session,
        detection_service: DetectionService,
    ) -> None:
        self._session = session
        self._detection_service = detection_service

    async def upload(
        self, entity: str, file: UploadFile, actor_id: int
    ) -> dict[str, Any]:
        return await upload_csv(
            entity,
            file,
            self._session,
            self._detection_service,
            actor_id,
        )

    def get_batch(self, batch_id: int) -> dict[str, Any]:
        return get_upload(batch_id, self._session)
