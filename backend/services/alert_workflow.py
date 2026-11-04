"""Alert decision workflow (API design 7.1).

Analyst: new -> closed (false positive) or new -> in_review (escalate).
Compliance: in_review -> confirmed_suspicious / closed / new (return).
Four eyes: whoever escalated an alert may not take the final decision on it.
"""

from collections.abc import Iterable


ALERT_STATUSES = ("new", "in_review", "closed", "confirmed_suspicious")

TRANSITIONS: dict[tuple[str, str], str] = {
    ("new", "closed"): "alert:update",
    ("new", "in_review"): "alert:escalate",
    ("in_review", "confirmed_suspicious"): "alert:confirm",
    ("in_review", "closed"): "alert:confirm",
    ("in_review", "new"): "alert:confirm",
}
# Leaving in_review towards one of these is a final decision and is subject to four eyes.
FOUR_EYES_TARGETS = frozenset({"confirmed_suspicious", "closed"})
NOTE_MAX_LENGTH = 2000
MAX_DECISION_ALERTS = 50

# Server error texts. The React app keeps the Turkish wording (K7); a test keeps
# both sides in sync, so change them together.
MSG_ALERT_NOT_FOUND = "Alert not found."
MSG_NO_TARGET_PERMISSION = "You are not allowed to move alerts to this status."
MSG_TRANSITION_NOT_ALLOWED = "This status transition is not allowed."
MSG_TRANSITION_PERMISSION = "You are not allowed to make this status transition."
MSG_FOUR_EYES = "The user who escalated this alert cannot decide on it."
MSG_NOTE_REQUIRED = "A note is required for every alert decision."
MSG_DIFFERENT_CUSTOMERS = "Selected alerts must belong to the same customer."
MSG_DIFFERENT_STATUSES = "Selected alerts must have the same status."


class WorkflowError(Exception):
    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        alert_id: int | None = None,
        access_denied: bool = False,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.alert_id = alert_id
        self.access_denied = access_denied


def permissions_for_target(target: str) -> set[str]:
    return {perm for (_, new), perm in TRANSITIONS.items() if new == target}


def ensure_target_permission(permissions: Iterable[str], target: str) -> None:
    """403 when the user cannot reach ``target`` through any transition."""
    if not permissions_for_target(target) & set(permissions):
        raise WorkflowError(403, MSG_NO_TARGET_PERMISSION, access_denied=True)


def check_transition(
    *,
    permissions: Iterable[str],
    user_id: int,
    alert_id: int,
    current: str,
    target: str,
    escalated_by: int | None,
) -> None:
    required = TRANSITIONS.get((current, target))
    if required is None:
        raise WorkflowError(422, MSG_TRANSITION_NOT_ALLOWED, alert_id=alert_id)
    if required not in set(permissions):
        raise WorkflowError(403, MSG_TRANSITION_PERMISSION, alert_id=alert_id)
    if (
        current == "in_review"
        and target in FOUR_EYES_TARGETS
        and escalated_by is not None
        and escalated_by == user_id
    ):
        raise WorkflowError(403, MSG_FOUR_EYES, alert_id=alert_id)


def normalize_note(note: str | None) -> str:
    normalized = (note or "").strip()
    if not normalized:
        raise WorkflowError(422, MSG_NOTE_REQUIRED)
    return normalized
