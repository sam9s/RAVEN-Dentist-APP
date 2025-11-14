"""Conversation session management utilities."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any, Dict, List, Tuple

from backend.services.cache import cache_get, cache_set

LOGGER = logging.getLogger(__name__)
SESSION_PREFIX = "raas:session:"
SESSION_TTL_SECONDS = 3600

DEFAULT_SESSION_STATE: Dict[str, Any] = {
    "status": "collecting_info",
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

    return state


def save_session(session_id: str, state: Dict[str, Any]) -> None:
    """Persist session state to Redis with a TTL."""

    cache_set(
        _session_key(session_id),
        json.dumps(state),
        ex=SESSION_TTL_SECONDS,
    )


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

    for field, (bucket, target_key) in PREFERENCE_FIELD_MAP.items():
        if field not in extracted:
            continue
        state.setdefault(bucket, {})
        state[bucket][target_key] = extracted[field]


def set_available_slots(
    state: Dict[str, Any],
    slots: List[Dict[str, Any]],
) -> None:
    """Store normalized available slots in the session payload."""

    state["available_slots"] = slots or []


def get_available_slots(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return any cached availability options for the session."""

    return state.get("available_slots", [])
