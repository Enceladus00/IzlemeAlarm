"""Response models (K10).

Every new or changed endpoint declares one of these as ``response_model``: fields
that are not declared here are dropped from the response, so a service that
accidentally returns extra personal data (e.g. a full name) cannot leak it.
The React app mirrors these shapes in frontend-v2/src/api/schemas/ (zod);
change both together.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


AlertStatus = Literal["new", "in_review", "closed", "confirmed_suspicious"]
Severity = Literal["low", "medium", "high"]


class AlertStatusResult(BaseModel):
    alert_id: int
    status: AlertStatus
    changed: bool


class DecisionResult(BaseModel):
    decision_id: str
    status: AlertStatus
    alert_ids: list[int]
    decided_at: datetime


# --- K1 alert queue ----------------------------------------------------------


class QueueSummary(BaseModel):
    alerts: int
    customers: int
    high_alerts: int
    high_customers: int
    returned_customers: int


class QueueEvent(BaseModel):
    old_status: str | None
    new_status: str
    changed_at: datetime
    actor_name: str | None


class AlertQueueItem(BaseModel):
    customer_no: str
    customer_name: str
    customer_type: str | None
    rule_codes: list[str]
    severity: Severity
    max_score: Decimal | None
    alert_count: int
    transaction_count: int
    oldest_created_at: datetime
    escalated_at: datetime | None
    alert_ids: list[int]
    last_event: QueueEvent | None
    returned_by: str | None
    returned_note: str | None
    # E04: the group's latest event is the escalation (new -> in_review).
    escalated_by: str | None = None
    escalation_note: str | None = None


class AlertQueuePage(BaseModel):
    summary: QueueSummary
    total: int
    items: list[AlertQueueItem]


# --- Alert detail (K8, K13) ---------------------------------------------------


class AlertCustomer(BaseModel):
    customer_no: str
    customer_name: str
    customer_type: str | None


class MaskedAlertTransaction(BaseModel):
    """What a user WITHOUT customer:view receives: no full names or account numbers."""

    view: Literal["masked"]
    transaction_id: int
    tx_time: datetime
    direction: Literal["in", "out"]
    amount: Decimal
    currency: str
    channel: str
    country_code: str
    counterparty: str
    counterparty_account: str
    in_alert: bool


class FullAlertTransaction(BaseModel):
    """Only for users with customer:view (compliance)."""

    view: Literal["full"]
    transaction_id: int
    transaction_no: str
    tx_time: datetime
    direction: Literal["in", "out"]
    amount: Decimal
    currency: str
    channel: str
    country_code: str
    sender_account_no: str
    sender_customer_no: str
    sender_customer_name: str
    receiver_account_no: str
    receiver_customer_no: str
    receiver_customer_name: str
    in_alert: bool


AlertTransactionItem = Annotated[
    MaskedAlertTransaction | FullAlertTransaction, Field(discriminator="view")
]


class HistoryItem(BaseModel):
    old_status: str | None
    new_status: str
    note: str | None
    changed_at: datetime
    changed_by: int
    actor_name: str | None
    actor_role: str | None


class EscalatedBy(BaseModel):
    user_id: int
    actor_name: str | None
    changed_at: datetime


class AlertEvent(BaseModel):
    action: str
    created_at: datetime
    details: dict[str, Any]


class ExplanationStep(BaseModel):
    step: int
    text: str
    status: str
    details: dict[str, Any]


class ExplanationRun(BaseModel):
    run_id: str
    as_of: datetime


class Explanation(BaseModel):
    rule_code: str
    rule_name: str
    alert_mode: str
    customer_type: str | None
    parameter_status: str
    raw_x: Decimal | None
    score: Decimal | None
    x_esik: str | None
    x_kesin: str | None
    parameters: dict[str, Any]
    steps: list[ExplanationStep]
    run: ExplanationRun


class AlertDetail(BaseModel):
    alert_id: int
    rule_code: str
    rule_name: str
    customer_no: str
    customer_name: str
    customer: AlertCustomer
    severity: Severity
    score: Decimal | None
    status: AlertStatus
    created_at: datetime
    transaction_count: int
    transaction_ids: list[int]
    transactions: list[AlertTransactionItem]
    history: list[HistoryItem]
    escalated_by: EscalatedBy | None
    explanation: Explanation | None
    events: list[AlertEvent]


# --- K4 customer context ------------------------------------------------------


class CustomerProfile(BaseModel):
    customer_type: str | None
    occupation: str | None
    monthly_income: Decimal | None
    risk_level: str | None
    customer_since: int | None


class MaskedAccount(BaseModel):
    account: str
    currency: str
    type: str | None


class CurrencySummary(BaseModel):
    currency: str
    incoming_30d: Decimal
    outgoing_30d: Decimal
    avg_monthly_outgoing_6m: Decimal


class CustomerContext(BaseModel):
    alert_id: int
    period_start: datetime
    profile: CustomerProfile
    accounts: list[MaskedAccount]
    summary: list[CurrencySummary]
    transactions: list[MaskedAlertTransaction]
    truncated: bool


# --- Transactions (compliance, customer:view) --------------------------------


class TransactionItem(BaseModel):
    transaction_id: int
    transaction_no: str
    amount: Decimal
    currency: str
    tx_time: datetime
    country_code: str
    channel: str
    sender_account_no: str
    sender_customer_no: str
    sender_customer_name: str
    receiver_account_no: str
    receiver_customer_no: str
    receiver_customer_name: str
    alert_linked: bool


class TransactionPage(BaseModel):
    total: int
    items: list[TransactionItem]


# --- My summary (alert queue KPI cards) ---------------------------------------


class ReturnedCase(BaseModel):
    customer_no: str
    customer_name: str
    rule_codes: list[str]
    alert_ids: list[int]
    returned_by: str | None
    returned_at: datetime
    note: str | None


class MyDecision(BaseModel):
    alert_id: int
    customer_no: str
    customer_name: str
    rule_code: str
    severity: str
    old_status: str | None
    new_status: str
    changed_at: datetime
    note: str | None


class MySummary(BaseModel):
    decided_today: int
    escalated_today: int
    returned_to_me: int
    returned_cases: list[ReturnedCase]
    queue_pending: int
    queue_high: int
    closed_today: int
    escalated_today_confirmed: int
    escalations_30d: int
    escalation_outcome_30d: "EscalationOutcome"
    decisions_today: list[MyDecision]


# --- Dashboards (K3) ----------------------------------------------------------


class TrendPoint(BaseModel):
    date: date
    alerts: int
    suspicious_transactions: int


class DashboardSummary(BaseModel):
    days: int
    customers: int
    accounts: int
    transactions: int
    alerts: int
    suspicious_transactions: int
    by_status: dict[str, int]
    by_severity: dict[str, int]
    by_rule: dict[str, int]
    trends: list[TrendPoint]


class EscalationOutcome(BaseModel):
    confirmed: int
    closed: int
    returned: int
    pending: int


# MySummary (above) refers to EscalationOutcome.
MySummary.model_rebuild()


class DashboardFunnel(BaseModel):
    days: int
    created: int
    open: int
    confirmed: int
    escalation_rate: float | None
    confirmed_rate: float | None
    avg_decision_days: float | None
    analyst_closed: int
    analyst_open: int
    escalated: int
    escalation_outcome: EscalationOutcome


class RulePerformance(BaseModel):
    rule_code: str
    name: str
    is_active: bool
    evaluated: int
    alerts: int
    avg_alert_score: Decimal | None
    confirmed: int
    closed: int
    hit_rate: float | None
    provisional: bool


# --- Audit log ------------------------------------------------------------------


class AuditEvent(BaseModel):
    audit_id: int
    actor_id: int | None
    actor_name: str | None
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, Any]
    created_at: datetime


class AuditLogPage(BaseModel):
    total: int
    items: list[AuditEvent]


# --- Rules, uploads, users, system ------------------------------------------------


class RuleFieldChange(BaseModel):
    field: str
    old: Any = None
    new: Any = None


class RuleHistoryEntry(BaseModel):
    change_id: int
    changed_at: datetime
    actor_name: str | None
    actor_role: str | None
    reason: str | None
    changes: list[RuleFieldChange]


class RuleView(BaseModel):
    rule_code: str
    is_active: bool
    weight: Decimal
    thresholds: dict[str, Any]


class UploadRowError(BaseModel):
    row_number: int
    reason: str
    row_data: dict[str, Any] | None


class UploadReport(BaseModel):
    batch_id: int
    entity_type: str
    file_name: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    uploaded_at: datetime
    own_upload: bool
    errors: list[UploadRowError]


class UploadSummary(BaseModel):
    batch_id: int
    entity_type: str
    file_name: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    uploaded_at: datetime
    uploaded_by_name: str | None


class UserView(BaseModel):
    user_id: int
    username: str
    role_code: str
    is_active: bool
    created_at: datetime | None


class SystemHealth(BaseModel):
    api: str
    database: str
    database_latency_ms: float
    schema_revision: str | None
    schema_head: str | None


class SystemRules(BaseModel):
    active: int
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_duration_ms: int | None


class SystemOverview(BaseModel):
    health: SystemHealth
    rules: SystemRules
    records: dict[str, Any]
    security: dict[str, Any]


# --- K12 transaction summary ------------------------------------------------------


class CurrencyTotals(BaseModel):
    currency: str
    total: Decimal
    incoming: Decimal | None
    outgoing: Decimal | None
    count: int
    incoming_count: int | None
    outgoing_count: int | None


class TimelinePoint(BaseModel):
    date: date
    count: int


class Timeline(BaseModel):
    granularity: Literal["day", "week"]
    points: list[TimelinePoint]


class FlowRoute(BaseModel):
    sender_account: str
    receiver_account: str
    sender_is_focus: bool
    receiver_is_focus: bool
    currency: str
    count: int
    amount: Decimal
    alert_linked: int


class OtherRoutes(BaseModel):
    route_count: int
    count: int


class TransactionSummary(BaseModel):
    transfer_count: int
    account_count: int
    by_currency: list[CurrencyTotals]
    timeline: Timeline
    routes: list[FlowRoute]
    other_routes: OtherRoutes


# --- Customers and accounts (customer:view) ---------------------------------------


class CustomerListItem(BaseModel):
    customer_no: str
    full_name: str
    customer_type: str | None
    risk_level: str | None
    is_active: bool
    account_count: int
    open_alert_count: int


class CustomerPage(BaseModel):
    total: int
    items: list[CustomerListItem]


class CustomerAccount(BaseModel):
    account_no: str
    currency: str
    account_type: str | None
    is_active: bool
    opened_at: date | None
    transaction_count: int


class CustomerAlertCounts(BaseModel):
    open: int
    total: int
    by_status: dict[str, int]


class CustomerProfileView(BaseModel):
    customer_no: str
    full_name: str
    customer_type: str | None
    occupation: str | None
    monthly_income: Decimal | None
    risk_level: str | None
    is_active: bool
    created_at: datetime | None
    accounts: list[CustomerAccount]
    alerts: CustomerAlertCounts


class MonthlyFlow(BaseModel):
    month: str
    currency: str
    incoming: Decimal
    outgoing: Decimal


class IncomeCheck(BaseModel):
    monthly_income: Decimal | None
    currency: str
    peak_month: str | None
    peak_direction: Literal["incoming", "outgoing"] | None
    peak_amount: Decimal | None
    ratio: Decimal | None
    threshold: Decimal
    exceeded: bool


class Counterparty(BaseModel):
    account_no: str
    customer_no: str
    customer_name: str
    currency: str
    count: int
    amount: Decimal
    is_new: bool


class CounterpartyFlows(BaseModel):
    incoming: list[Counterparty]
    outgoing: list[Counterparty]


class CustomerAnalysis(BaseModel):
    customer_no: str
    days: int
    date_from: date
    date_to: date
    monthly: list[MonthlyFlow]
    income_check: IncomeCheck
    counterparties: CounterpartyFlows


class AccountListItem(BaseModel):
    account_no: str
    customer_no: str
    customer_name: str
    currency: str
    account_type: str | None
    is_active: bool
    opened_at: date | None


class AccountPage(BaseModel):
    total: int
    items: list[AccountListItem]

