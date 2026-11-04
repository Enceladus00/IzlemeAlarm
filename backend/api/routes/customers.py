from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies import get_customer_service, require_permission
from backend.api.responses import AccountPage, CustomerPage, CustomerProfileView
from backend.repositories.customer_repository import AccountFilters, CustomerFilters
from backend.repositories.customer_view_log import CustomerViewLogFailed
from backend.services.auth_service import AuthenticatedUser
from backend.services.customer_service import CustomerNotFound, CustomerService


router = APIRouter(tags=["customers"])


@router.get("/customers", response_model=CustomerPage)
def list_customers(
    q: str | None = Query(default=None, max_length=100),
    customer_type: Literal["BIREYSEL", "KURUMSAL"] | None = None,
    risk_level: Literal["low", "medium", "high"] | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    _user: AuthenticatedUser = Depends(require_permission("customer:view")),
    service: CustomerService = Depends(get_customer_service),
) -> Any:
    filters = CustomerFilters(
        q=(q or "").strip() or None,
        customer_type=customer_type,
        risk_level=risk_level,
        offset=offset,
        limit=limit,
    )
    try:
        return service.list_customers(filters)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load customers.") from exc


@router.get("/customers/{customer_no}", response_model=CustomerProfileView)
def get_customer(
    customer_no: str,
    user: AuthenticatedUser = Depends(require_permission("customer:view")),
    service: CustomerService = Depends(get_customer_service),
) -> Any:
    try:
        return service.get_customer(customer_no, user.user_id)
    except CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CustomerViewLogFailed as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load customers.") from exc


@router.get("/accounts", response_model=AccountPage)
def list_accounts(
    q: str | None = Query(default=None, max_length=100),
    customer_no: str | None = Query(default=None, max_length=20),
    currency: str | None = Query(default=None, pattern="^[A-Z]{3}$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthenticatedUser = Depends(require_permission("customer:view")),
    service: CustomerService = Depends(get_customer_service),
) -> Any:
    filters = AccountFilters(
        q=(q or "").strip() or None,
        customer_no=customer_no,
        currency=currency,
        offset=offset,
        limit=limit,
    )
    try:
        return service.list_accounts(filters, user.user_id)
    except CustomerViewLogFailed as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not load accounts.") from exc
