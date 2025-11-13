"""LLM client abstraction for RAAS conversations."""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

LOGGER = logging.getLogger(__name__)


class LLMAction(BaseModel):
    """Structured action directive emitted by the LLM."""

    type: Literal[
        "COLLECT_INFO",
        "CHECK_AVAILABILITY",
        "AWAIT_SLOT_SELECTION",
        "BOOK_SLOT",
        "SESSION_COMPLETE",
    ]
    missing_fields: Optional[list[str]] = None
    slot_index: Optional[int] = None
    slot_id: Optional[str] = None


class LLMResponse(BaseModel):
    """Normalized LLM response payload."""

    reply_to_user: str
    action: LLMAction
    extracted: Dict[str, Any] = Field(default_factory=dict)


class RAASLLMClient:
    """Facade over the OpenAI client with graceful fallbacks."""

    def __init__(self, api_key: Optional[str], model: str) -> None:
        self.api_key = api_key or ""
        self.model = model
        self._client = None

        if self.api_key:
            try:
                # Imported lazily to avoid heavy import cost.
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Failed to initialize OpenAI client: %s", exc)
                self._client = None

    def generate_response(
        self,
        *,
        session: Dict[str, Any],
        message_text: str,
        channel: str,
    ) -> LLMResponse:
        """Generate an LLM response or return a deterministic fallback."""

        if not self._client:
            LOGGER.info(
                "OpenAI client unavailable; returning fallback response",
            )
            return self._fallback_response(session=session, message_text=message_text)

        try:
            # Placeholder until full prompt contract is implemented.
            LOGGER.debug("Invoking OpenAI model %s", self.model)
            # The real implementation will call `self._client.responses.create(...)`.
            # Returning fallback in the interim keeps the flow deterministic.
            return self._fallback_response(
                session=session,
                message_text=message_text,
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("OpenAI call failed; using fallback response: %s", exc)
            return self._fallback_response(
                session=session,
                message_text=message_text,
            )

    @staticmethod
    def _fallback_response(
        *, session: Dict[str, Any], message_text: str
    ) -> LLMResponse:
        """Return a deterministic stub output for development and testing."""

        extracted: Dict[str, Any] = {}
        if "name" not in session.get("patient", {}) and message_text.strip():
            extracted["patient_name"] = message_text.strip()

        action = LLMAction(type="COLLECT_INFO", missing_fields=[])

        return LLMResponse(
            reply_to_user=(
                "Thanks, I've recorded that. "
                "What else should I note?"
            ),
            action=action,
            extracted=extracted,
        )
