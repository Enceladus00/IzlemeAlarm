"""Server-side masking of personal data (K4, K13).

Masking must happen on the server: anything sent to the browser can be read in
the developer tools, even when the screen does not show it.
"""

from typing import Any

from backend.models import Customer, Transaction


ELLIPSIS = "…"


def _initial(word: str) -> str:
    return f"{word[0]}." if word else ""


def mask_name(full_name: str | None, customer_type: str | None) -> str:
    """BIREYSEL: initials then the last word ("Ömer Kılıç" -> "Ö. Kılıç").
    KURUMSAL: first word, then initials ("Nehir Lojistik A.Ş." -> "Nehir L. A.")."""
    words = (full_name or "").split()
    if not words:
        return ""
    if customer_type == "KURUMSAL":
        return " ".join([words[0], *(_initial(word) for word in words[1:])])
    return " ".join([*(_initial(word) for word in words[:-1]), words[-1]])


def mask_account(account_no: str | None) -> str:
    value = (account_no or "").strip()
    return ELLIPSIS + value[-4:] if value else ""


def transaction_direction(transaction: Transaction, customer_id: int) -> str:
    """'out' when the customer sent the money, otherwise 'in'."""
    return "out" if transaction.sender_account.customer_id == customer_id else "in"


def _counterparty(transaction: Transaction, customer_id: int):
    if transaction_direction(transaction, customer_id) == "out":
        return transaction.receiver_account
    return transaction.sender_account


def masked_transaction(
    transaction: Transaction, customer_id: int, *, in_alert: bool
) -> dict[str, Any]:
    counterparty_account = _counterparty(transaction, customer_id)
    counterparty: Customer = counterparty_account.customer
    return {
        "view": "masked",
        "transaction_id": transaction.transaction_id,
        "tx_time": transaction.tx_time,
        "direction": transaction_direction(transaction, customer_id),
        "amount": transaction.amount,
        "currency": transaction.currency,
        "channel": transaction.channel,
        "country_code": transaction.country_code,
        "counterparty": mask_name(counterparty.full_name, counterparty.customer_type),
        "counterparty_account": mask_account(counterparty_account.account_no),
        "in_alert": in_alert,
    }
