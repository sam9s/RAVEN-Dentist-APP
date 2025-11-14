"""Chat conversation router for RAAS."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.llm import RAASLLMClient
from backend.services.session import (
    append_history,
    get_available_slots,
    load_session,
    merge_extracted_data,
    save_session,
    set_available_slots,
)
from backend.utils.config import get_settings
from calendar_service.cal_adapter import CalComAdapter

LOGGER = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()
llm_client = RAASLLMClient(
    api_key=settings.openai_api_key,
    model=settings.openai_model,
    temperature=settings.openai_temperature,
    use_stub=settings.openai_use_stub,
)
calendar_client = CalComAdapter(api_key=settings.cal_api_key)


class ChatRequest(BaseModel):
    """Inbound chat payload from Slack or web UI."""

    session_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    message_text: str = Field(default="")


class ChatResponse(BaseModel):
    """Outbound response contract consumed by channel adapters."""

    session_id: str
    reply_to_user: str
    action: Dict[str, Any]


@router.post("/chat", response_model=ChatResponse)
def handle_chat_message(payload: ChatRequest) -> ChatResponse:
    """Process a chat message through session + LLM layers."""

    LOGGER.debug(
        "Processing chat message for session=%s channel=%s",
        payload.session_id,
        payload.channel,
    )

    session_state = load_session(payload.session_id)
    append_history(session_state, "user", payload.message_text)

    llm_result = llm_client.generate_response(
        session=session_state,
        message_text=payload.message_text,
        channel=payload.channel,
    )

    merge_extracted_data(session_state, llm_result.extracted)
    append_history(session_state, "assistant", llm_result.reply_to_user)

    action_type = llm_result.action.type
    session_state["status"] = action_type.lower()
    metadata = session_state.setdefault("metadata", {})
    metadata["last_action"] = action_type

    try:
        _execute_action(
            action_type=action_type,
            session_state=session_state,
            action_payload=llm_result.action.model_dump(),
        )
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("Action handler failed: action=%s error=%s", action_type, exc)
        metadata["action_error"] = str(exc)

    save_session(payload.session_id, session_state)

    response = ChatResponse(
        session_id=payload.session_id,
        reply_to_user=llm_result.reply_to_user,
        action=llm_result.action.model_dump(),
    )

    LOGGER.debug(
        "Responding to session=%s with action=%s",
        payload.session_id,
        llm_result.action.type,
    )
    return response


def _execute_action(
    *,
    action_type: str,
    session_state: Dict[str, Any],
    action_payload: Dict[str, Any],
) -> None:
    """Perform backend side-effects for the given action."""

    metadata = session_state.setdefault("metadata", {})

    if action_type == "CHECK_AVAILABILITY":
        preferences = session_state.get("preferences", {})
        slots = calendar_client.check_availability(preferences)
        set_available_slots(session_state, slots)
        metadata["available_slot_count"] = len(slots)
        return

    if action_type == "BOOK_SLOT":
        booking = _book_selected_slot(session_state, action_payload)
        if booking:
            metadata["latest_booking"] = booking
        else:
            metadata["booking_error"] = "slot_not_found"
        return

    if action_type == "SESSION_COMPLETE":
        metadata["session_closed"] = True


def _book_selected_slot(
    session_state: Dict[str, Any],
    action_payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Invoke booking flow for the slot referenced in the action."""

    slots = get_available_slots(session_state)
    if not slots:
        return None

    slot: Optional[Dict[str, Any]] = None
    slot_index = action_payload.get("slot_index")
    slot_id = action_payload.get("slot_id")

    if isinstance(slot_index, int) and 0 <= slot_index < len(slots):
        slot = slots[slot_index]
    elif slot_id:
        slot = next((item for item in slots if item.get("slot_id") == slot_id), None)

    if not slot:
        return None

    patient = session_state.get("patient", {})
    booking = calendar_client.book_appointment(slot=slot, patient=patient)
    return booking
