"""Chat conversation router for RAAS."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.llm import RAASLLMClient
from backend.services.session import (
    append_history,
    load_session,
    merge_extracted_data,
    save_session,
)
from backend.utils.config import get_settings

LOGGER = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()
llm_client = RAASLLMClient(
    api_key=settings.openai_api_key,
    model=settings.openai_model,
)


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
