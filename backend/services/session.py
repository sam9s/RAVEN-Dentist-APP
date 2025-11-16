"""Conversation session management utilities."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.services.cache import cache_delete, cache_get, cache_set

LOGGER = logging.getLogger(__name__)
SESSION_PREFIX = "raas:session:"
SESSION_TTL_SECONDS = 3600

SESSION_STATUS_DEFAULT = "NEW"
TERMINAL_STATUSES = {"CONFIRMED", "CANCELLED", "CLOSED"}

STATUS_PRIORITY: Dict[str, int] = {
    "NEW": 0,
    "GREETING": 1,
    "COLLECTING_INFO": 2,
    "AWAITING_SLOT_SELECTION": 3,
    "BOOKING": 4,
    "PENDING": 5,
    "RESCHEDULE_REQUESTED": 6,
    "CONFIRMED": 7,
    "CANCELLED": 7,
    "CLOSED": 8,
}

ACTION_STATUS_MAP: Dict[str, str] = {
    "COLLECT_INFO": "COLLECTING_INFO",
    "CHECK_AVAILABILITY": "COLLECTING_INFO",
    "AWAIT_SLOT_SELECTION": "AWAITING_SLOT_SELECTION",
    "BOOK_SLOT": "BOOKING",
    "CONFIRMATION_PROMPT": "BOOKING",
    "REQUEST_RESCHEDULE": "RESCHEDULE_REQUESTED",
    "CANCEL_BOOKING": "CANCELLED",
    "SESSION_COMPLETE": "CLOSED",
}

BOOKING_STATUS_VALUES = {"PENDING", "CONFIRMED", "CANCELLED"}


DEFAULT_SESSION_STATE: Dict[str, Any] = {
    "status": SESSION_STATUS_DEFAULT,
    "patient": {},
    "preferences": {},
    "available_slots": [],
    "extracted": {},
    "history": [],
    "metadata": {},
}

PATIENT_FIELD_MAP: Dict[str, Tuple[str, str]] = {
    "patient_name": ("patient", "name"),
    "patient_phone": ("patient", "phone"),
    "patient_email": ("patient", "email"),
}

PREFERENCE_FIELD_MAP: Dict[str, Tuple[str, str]] = {
    "preferred_date": ("preferences", "date"),
    "preferred_time_window": ("preferences", "time_window"),
    "dentist_id": ("preferences", "dentist_id"),
    "service_type": ("preferences", "service_type"),
    "reason": ("preferences", "reason"),
}

HISTORY_MAX_ENTRIES = 10


def _session_key(session_id: str) -> str:
    return f"{SESSION_PREFIX}{session_id}"


def new_session_state() -> Dict[str, Any]:
    """Return an isolated copy of the default session payload."""

    return deepcopy(DEFAULT_SESSION_STATE)


def load_session(session_id: str) -> Dict[str, Any]:
    """Load a session from Redis, creating a new one if missing."""

    raw_state = cache_get(_session_key(session_id))
    if raw_state is None:
        LOGGER.debug(
            "Session %s not found; creating new state",
            session_id,
        )
        return new_session_state()

    try:
        state: Dict[str, Any] = json.loads(raw_state)
    except json.JSONDecodeError:
        LOGGER.warning(
            "Session %s payload invalid JSON; resetting",
            session_id,
        )
        return new_session_state()

    if is_session_terminal(state):
        LOGGER.debug("Session %s is terminal; resetting state", session_id)
        delete_session(session_id)
        return new_session_state()

    return state


def save_session(session_id: str, state: Dict[str, Any]) -> None:
    """Persist session state to Redis with a TTL."""

    cache_set(
        _session_key(session_id),
        json.dumps(state),
        ex=SESSION_TTL_SECONDS,
    )


def delete_session(session_id: str) -> None:
    """Remove a session from Redis."""

    cache_delete(_session_key(session_id))


def is_session_terminal(state: Dict[str, Any]) -> bool:
    """Return True when the session should no longer persist."""

    status = state.get("status", SESSION_STATUS_DEFAULT)
    if status in TERMINAL_STATUSES:
        return True

    metadata = state.get("metadata") or {}
    if metadata.get("session_closed"):
        return True

    booking = metadata.get("latest_booking")
    if booking:
        booking_status = str(booking.get("status", "")).upper()
        if booking_status in TERMINAL_STATUSES:
            return True

    return False


def append_history(state: Dict[str, Any], role: str, content: str) -> None:
    """Append a conversation turn to the session history."""

    state.setdefault("history", [])
    history_entry = {
        "role": role,
        "content": content,
    }
    state["history"].append(history_entry)
    overflow = len(state["history"]) - HISTORY_MAX_ENTRIES
    if overflow > 0:
        del state["history"][:overflow]


def merge_extracted_data(
    state: Dict[str, Any],
    extracted: Dict[str, Any],
) -> None:
    """Merge extracted LLM data into the session record."""

    if not extracted:
        return

    state.setdefault("extracted", {})
    for key, value in extracted.items():
        if value is None:
            continue
        state["extracted"][key] = value

    _apply_structured_fields(state, extracted)


def update_status_for_action(state: Dict[str, Any], action_type: str) -> None:
    """Transition the session status based on the emitted action."""

    if not action_type:
        return

    next_status = ACTION_STATUS_MAP.get(action_type)

    if (
        action_type == "SMALL_TALK"
        and state.get("status", SESSION_STATUS_DEFAULT) == SESSION_STATUS_DEFAULT
    ):
        next_status = "GREETING"

    if not next_status:
        return

    current_status = state.get("status", SESSION_STATUS_DEFAULT)
    if STATUS_PRIORITY.get(next_status, 0) >= STATUS_PRIORITY.get(current_status, 0):
        state["status"] = next_status


def apply_booking_status(state: Dict[str, Any], booking: Optional[Dict[str, Any]]) -> None:
    """Elevate session status based on booking lifecycle status."""

    if not booking:
        return

    status_value = booking.get("status")
    if not status_value:
        return

    normalized = str(status_value).upper()
    if normalized not in BOOKING_STATUS_VALUES:
        return

    current_status = state.get("status", SESSION_STATUS_DEFAULT)
    if STATUS_PRIORITY.get(normalized, 0) >= STATUS_PRIORITY.get(current_status, 0):
        state["status"] = normalized


def _apply_structured_fields(
    state: Dict[str, Any],
    extracted: Dict[str, Any],
) -> None:
    """Populate patient and preference sub-objects from extracted data."""

    for field, (bucket, target_key) in PATIENT_FIELD_MAP.items():
        if field not in extracted:
            continue
        state.setdefault(bucket, {})
        state[bucket][target_key] = extracted[field]
        if field == "patient_email" and extracted[field]:
            metadata = state.setdefault("metadata", {})
            if metadata.get("booking_error") == "missing_patient_email":
                metadata.pop("booking_error", None)

    for field, (bucket, target_key) in PREFERENCE_FIELD_MAP.items():
        if field not in extracted:
            continue

        if field == "preferred_date":
            normalized, error = _normalize_preferred_date(extracted[field])
            metadata = state.setdefault("metadata", {})
            if error:
                metadata["preferred_date_error"] = error
                extracted[field] = None
                state.setdefault(bucket, {}).pop(target_key, None)
                continue

            metadata.pop("preferred_date_error", None)
            extracted[field] = normalized
            value = normalized
        else:
            value = extracted[field]

        state.setdefault(bucket, {})
        state[bucket][target_key] = value


def _normalize_preferred_date(value: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return normalized YYYY-MM-DD or an error code."""

    if value is None:
        return None, "missing"

    raw = str(value).strip()
    if not raw:
        return None, "invalid_format"

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None, "invalid_format"

    target_date = parsed.date()
    today = datetime.now().date()
    if target_date < today:
        return None, "past_date"

    return target_date.isoformat(), None


def set_available_slots(
    state: Dict[str, Any],
    slots: List[Dict[str, Any]],
) -> None:
    """Store normalized available slots in the session payload."""

    state["available_slots"] = slots or []


def get_available_slots(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return any cached availability options for the session."""

    return state.get("available_slots", [])
