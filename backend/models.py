from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customer"

    customer_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    customer_no: Mapped[str] = mapped_column(String(20), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    customer_type: Mapped[str | None] = mapped_column(String(10))
    occupation: Mapped[str | None] = mapped_column(String(50))
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    risk_level: Mapped[str | None] = mapped_column(String(6))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    accounts: Mapped[list["Account"]] = relationship(back_populates="customer")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="customer")


class Account(Base):
    __tablename__ = "account"

    account_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    account_no: Mapped[str] = mapped_column(String(34), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.customer_id"))
    currency: Mapped[str] = mapped_column(CHAR(3))
    account_type: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    opened_at: Mapped[date | None] = mapped_column(Date)
    customer: Mapped[Customer] = relationship(back_populates="accounts")
    sent_transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="sender_account", foreign_keys="Transaction.sender_account_id"
    )
    received_transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="receiver_account", foreign_keys="Transaction.receiver_account_id"
    )


class Transaction(Base):
    __tablename__ = "transaction"
    __table_args__ = (
        CheckConstraint("amount > 0"),
        CheckConstraint("channel IN ('atm', 'mobile', 'internet', 'branch')"),
        CheckConstraint("country_code ~ '^[A-Z]{2}$'"),
        Index("idx_transaction_sender_time", "sender_account_id", "tx_time"),
        Index("idx_transaction_receiver_time", "receiver_account_id", "tx_time"),
    )

    transaction_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    transaction_no: Mapped[str] = mapped_column(String(30), unique=True)
    sender_account_id: Mapped[int] = mapped_column(ForeignKey("account.account_id"))
    receiver_account_id: Mapped[int] = mapped_column(ForeignKey("account.account_id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(CHAR(3))
    tx_time: Mapped[datetime] = mapped_column(DateTime)
    channel: Mapped[str] = mapped_column(String(10))
    country_code: Mapped[str] = mapped_column(CHAR(2))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    sender_account: Mapped[Account] = relationship(
        back_populates="sent_transactions", foreign_keys=[sender_account_id]
    )
    receiver_account: Mapped[Account] = relationship(
        back_populates="received_transactions", foreign_keys=[receiver_account_id]
    )


class AppUser(Base):
    __tablename__ = "app_user"

    user_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )


class MonitoringRule(Base):
    __tablename__ = "monitoring_rule"

    rule_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    rule_code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    thresholds: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))


class RuleChangeLog(Base):
    __tablename__ = "rule_change_log"

    change_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("monitoring_rule.rule_id"))
    changed_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    old_thresholds: Mapped[dict[str, Any]] = mapped_column(JSONB)
    new_thresholds: Mapped[dict[str, Any]] = mapped_column(JSONB)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )


class UploadBatch(Base):
    __tablename__ = "upload_batch"

    batch_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    entity_type: Mapped[str] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(Text)
    total_rows: Mapped[int] = mapped_column(server_default=text("0"))
    accepted_rows: Mapped[int] = mapped_column(server_default=text("0"))
    rejected_rows: Mapped[int] = mapped_column(server_default=text("0"))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    errors: Mapped[list["UploadRowError"]] = relationship(back_populates="batch")


class UploadRowError(Base):
    __tablename__ = "upload_row_error"

    row_error_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.batch_id"))
    row_number: Mapped[int] = mapped_column()
    reason: Mapped[str] = mapped_column(Text)
    row_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    batch: Mapped[UploadBatch] = relationship(back_populates="errors")


class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = (
        Index("idx_alert_status_created_at", "status", text("created_at DESC")),
        Index("idx_alert_customer_id", "customer_id"),
    )

    alert_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("monitoring_rule.rule_id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.customer_id"))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(
        String(30), server_default=text("'new'")
    )
    deduplication_key: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    customer: Mapped[Customer] = relationship(back_populates="alerts")
    rule: Mapped[MonitoringRule] = relationship()
    transactions: Mapped[list["AlertTransaction"]] = relationship(
        back_populates="alert"
    )
    history: Mapped[list["AlertStatusHistory"]] = relationship(
        back_populates="alert", order_by="AlertStatusHistory.changed_at"
    )


class AlertTransaction(Base):
    __tablename__ = "alert_transaction"

    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alert.alert_id"), primary_key=True
    )
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transaction.transaction_id"), primary_key=True
    )
    alert: Mapped[Alert] = relationship(back_populates="transactions")
    transaction: Mapped[Transaction] = relationship()


class AlertStatusHistory(Base):
    __tablename__ = "alert_status_history"
    __table_args__ = (
        CheckConstraint(
            "new_status IN ('new', 'in_review', 'closed', 'confirmed_suspicious')"
        ),
        CheckConstraint(
            "new_status NOT IN ('closed', 'confirmed_suspicious') OR "
            "NULLIF(BTRIM(note), '') IS NOT NULL"
        ),
    )

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alert.alert_id"))
    changed_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    old_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    alert: Mapped[Alert] = relationship(back_populates="history")


class AuditLog(Base):
    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
