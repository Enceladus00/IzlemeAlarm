from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies import get_transaction_service, require_permission
from backend.services.auth_service import AuthenticatedUser
from backend.api.responses import TransactionPage, TransactionSummary
from backend.repositories.customer_view_log import CustomerViewLogFailed
from backend.services.transaction_service import (
    InvalidTransactionFilters,
    TransactionService,
)


router = APIRouter()


@router.get("/transactions/summary", response_model=TransactionSummary)
def transaction_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    customer_no: str | None = Query(default=None, max_length=20),
    account_no: str | None = Query(default=None, max_length=34),
    direction: str | None = Query(default=None, pattern="^(incoming|outgoing)$"),
    min_amount: Decimal | None = Query(default=None, gt=0),
    max_amount: Decimal | None = Query(default=None, gt=0),
    account_ref: str | None = Query(default=None, max_length=64),
    user: AuthenticatedUser = Depends(require_permission("customer:view")),
    service: TransactionService = Depends(get_transaction_service),
) -> Any:
    try:
        return service.summary(
            account_ref=account_ref,
            actor_id=user.user_id,
            date_from=date_from,
            date_to=date_to,
            customer_no=customer_no,
            account_no=account_no,
            direction=direction,
            min_amount=min_amount,
            max_amount=max_amount,
        )
    except InvalidTransactionFilters as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CustomerViewLogFailed as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load transactions.") from exc


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    date_from: date | None = None,
    date_to: date | None = None,
    customer_no: str | None = None,
    account_no: str | None = Query(default=None, max_length=34),
    direction: str | None = Query(default=None, pattern="^(incoming|outgoing)$"),
    min_amount: Decimal | None = Query(default=None, gt=0),
    max_amount: Decimal | None = Query(default=None, gt=0),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    user: AuthenticatedUser = Depends(require_permission("customer:view")),
    service: TransactionService = Depends(get_transaction_service),
) -> Any:
    try:
        return service.list_transactions(
            actor_id=user.user_id,
            date_from=date_from,
            date_to=date_to,
            customer_no=customer_no,
            account_no=account_no,
            direction=direction,
            min_amount=min_amount,
            max_amount=max_amount,
            offset=offset,
            limit=limit,
        )
    except InvalidTransactionFilters as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CustomerViewLogFailed as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load transactions.") from exc
