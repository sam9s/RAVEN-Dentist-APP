"""Conversation session management utilities."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any, Dict

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
}


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


def merge_extracted_data(state: Dict[str, Any], extracted: Dict[str, Any]) -> None:
    """Merge extracted LLM data into the session record."""

    if not extracted:
        return

    state.setdefault("extracted", {})
    for key, value in extracted.items():
        if value is not None:
            state["extracted"][key] = value
