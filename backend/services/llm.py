"""LLM client abstraction for RAAS conversations."""

from __future__ import annotations

import json
import logging
import re
from textwrap import dedent
from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = dedent(
    """
    You are RAAS Assistant — the polite, concise receptionist for Dentist Verma Clinic.
    * Scope: Dentistry appointments only.
    * Tone: Professional, warm, and efficient.
    * Restricted: Do not offer medical advice, billing resolutions, or tech details.
    * Escalation: Offer to connect with staff for out-of-scope requests.
    * Timezone: Asia/Kolkata. Dates must be ISO (YYYY-MM-DD).
    * Output: ALWAYS return a single JSON object matching the schema. No prose.
    * On serialization error: return {"error": "INVALID_JSON"}.
    """
).strip()

DATE_HANDLING_GUIDANCE = dedent(
    """
    Date handling requirements:
    - Always collect appointment dates in full ISO format (YYYY-MM-DD).
    - If session.metadata.preferred_date_error == "invalid_format", inform the
      user their date was invalid and request a correct YYYY-MM-DD date.
    - If session.metadata.preferred_date_error == "past_date", tell the user the
      date is in the past and ask for a future date in YYYY-MM-DD format.
    """
).strip()

CONTACT_REQUIREMENTS = dedent(
    """
    Contact details:
    - patient_phone and patient_email must be captured before booking.
    - If session.patient.email is missing or
      session.metadata.booking_error == "missing_patient_email", ask for the
      email before proceeding.
    - If patient details seem unclear, confirm them explicitly.
    """
).strip()

ALLOWED_ACTIONS_TEXT = dedent(
    """
    Allowed action.type values: COLLECT_INFO, CHECK_AVAILABILITY,
    AWAIT_SLOT_SELECTION, BOOK_SLOT, REQUEST_RESCHEDULE, CANCEL_BOOKING,
    CONFIRMATION_PROMPT, SESSION_COMPLETE, SMALL_TALK, CONNECT_STAFF.
    Do not use any other value.
    """
).strip()

JSON_RESPONSE_EXAMPLE = dedent(
    """
    Example JSON response:
    {
      "reply_to_user": "Hello — may I have your full name?",
      "action": {
        "type": "COLLECT_INFO",
        "missing_fields": ["patient_name"],
        "slot_index": null,
        "slot_id": null,
        "notes": null
      },
      "extracted": {
        "patient_name": null,
        "patient_phone": null,
        "patient_email": null,
        "preferred_date": null,
        "preferred_time_window": null,
        "service_type": null,
        "dentist_id": null,
        "reason": null
      }
    }
    Do not wrap this JSON in markdown fences. Always fill unspecified keys with null.
    """
).strip()


class LLMAction(BaseModel):
    """Structured action directive emitted by the LLM."""

    type: Literal[
        "COLLECT_INFO",
        "CHECK_AVAILABILITY",
        "AWAIT_SLOT_SELECTION",
        "BOOK_SLOT",
        "REQUEST_RESCHEDULE",
        "CANCEL_BOOKING",
        "CONFIRMATION_PROMPT",
        "SESSION_COMPLETE",
        "SMALL_TALK",
        "CONNECT_STAFF",
    ]
    missing_fields: Optional[List[str]] = None
    slot_index: Optional[int] = None
    slot_id: Optional[str] = None
    notes: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("notes", "explain"),
        serialization_alias="notes",
    )

    model_config = ConfigDict(populate_by_name=True)


class LLMResponse(BaseModel):
    """Normalized LLM response payload."""

    reply_to_user: str
    action: LLMAction
    extracted: Dict[str, Any] = Field(default_factory=dict)


class RAASLLMClient:
    """Facade over the OpenAI client with graceful fallbacks."""

    def __init__(
        self,
        api_key: Optional[str],
        model: str,
        *,
        temperature: float = 0.1,
        use_stub: bool = False,
    ) -> None:
        self.api_key = api_key or ""
        self.model = model
        self.temperature = temperature
        self.use_stub = use_stub or not self.api_key
        self._client = None

        if self.api_key and not self.use_stub:
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
        """Generate an LLM response from OpenAI or a deterministic stub."""

        cleaned_message = message_text.strip()

        if self.use_stub or not self._client:
            LOGGER.debug("Using stubbed LLM response path")
            return self._stub_response(
                session=session,
                message_text=cleaned_message,
            )

        try:
            raw_output = self._call_openai(
                session=session,
                message_text=cleaned_message,
                channel=channel,
            )
            return self._parse_llm_output(raw_output)
        except (ValueError, ValidationError) as exc:
            LOGGER.error("Invalid LLM output; falling back. error=%s", exc)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("OpenAI call failed; using fallback response: %s", exc)

        return self._stub_response(
            session=session,
            message_text=cleaned_message,
        )

    def _call_openai(
        self,
        *,
        session: Dict[str, Any],
        message_text: str,
        channel: str,
    ) -> str:
        """Invoke OpenAI Responses API and return raw text content."""

        if not self._client:  # pragma: no cover - defensive
            raise RuntimeError("OpenAI client unavailable")

        messages = self._build_messages(
            session=session,
            message_text=message_text,
            channel=channel,
        )

        response = self._client.responses.create(
            model=self.model,
            input=messages,
            temperature=self.temperature,
        )

        text_chunks: List[str] = []
        for item in getattr(response, "output", []) or []:
            for part in getattr(item, "content", []) or []:
                if getattr(part, "type", None) == "output_text":
                    text_chunks.append(getattr(part, "text", ""))

        raw_text = "".join(text_chunks).strip()
        if not raw_text:
            raise ValueError("Empty response from OpenAI")

        LOGGER.debug("OpenAI raw output (truncated): %s", raw_text[:500])
        return raw_text

    def _build_messages(
        self,
        *,
        session: Dict[str, Any],
        message_text: str,
        channel: str,
    ) -> List[Dict[str, Any]]:
        """Render conversation context for the LLM prompt."""

        context = self._render_context(session=session, channel=channel)
        history = self._render_history(session=session)

        developer_prompt = dedent(
            """
            Conversation context (JSON):
            {context}

            Recent dialogue:
            {history}

            Latest user message:
            """
        ).strip().format(context=context, history=history)

        instructions = "\n\n".join(
            [
                developer_prompt,
                CONTACT_REQUIREMENTS,
                DATE_HANDLING_GUIDANCE,
                ALLOWED_ACTIONS_TEXT,
                JSON_RESPONSE_EXAMPLE,
            ]
        )

        user_payload = f"{instructions}\n{message_text or ''}".strip()

        messages = [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": SYSTEM_PROMPT},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_payload},
                ],
            },
        ]

        return messages

    def _render_context(self, *, session: Dict[str, Any], channel: str) -> str:
        """Serialize structured session data for the prompt."""

        patient = session.get("patient", {})
        preferences = session.get("preferences", {})
        available_slots = session.get("available_slots", [])[:5]

        payload = {
            "channel": channel,
            "patient": patient,
            "preferences": preferences,
            "available_slots": available_slots,
            "metadata": session.get("metadata", {}),
        }

        return json.dumps(payload, ensure_ascii=False, default=str)

    def _render_history(self, *, session: Dict[str, Any]) -> str:
        """Return the condensed recent dialogue from session history."""

        history = session.get("history", [])[-5:]
        if not history:
            return "<no history>"

        lines = [
            f"{item['role']}: {item['content']}" for item in history
        ]
        return "\n".join(lines)

    @staticmethod
    def _parse_llm_output(raw_output: str) -> LLMResponse:
        """Validate and coerce OpenAI output into LLMResponse."""

        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            LOGGER.debug("Raw LLM output (truncated): %s", raw_output[:500])
            raise ValueError("LLM did not return valid JSON") from exc

        try:
            return LLMResponse.model_validate(payload)
        except ValidationError as exc:
            LOGGER.debug(
                "LLM payload failed validation: %s", json.dumps(payload)[:500]
            )
            raise

    def _stub_response(
        self,
        *,
        session: Dict[str, Any],
        message_text: str,
    ) -> LLMResponse:
        """Rule-based fallback that mirrors the designed flow."""

        metadata = session.setdefault("metadata", {})
        extracted = self._extract_stub_fields(message_text)

        proposed_patient = dict(session.get("patient", {}))
        proposed_preferences = dict(session.get("preferences", {}))

        if "patient_name" in extracted:
            proposed_patient["name"] = extracted["patient_name"]
        if "patient_phone" in extracted:
            proposed_patient["phone"] = extracted["patient_phone"]
        if "patient_email" in extracted:
            proposed_patient["email"] = extracted["patient_email"]
        if "preferred_date" in extracted:
            proposed_preferences["date"] = extracted["preferred_date"]
        if "preferred_time_window" in extracted:
            proposed_preferences["time_window"] = extracted[
                "preferred_time_window"
            ]
        if "dentist_id" in extracted:
            proposed_preferences["dentist_id"] = extracted["dentist_id"]
        if "reason" in extracted:
            proposed_preferences["reason"] = extracted["reason"]

        missing_fields: List[str] = []
        if not proposed_patient.get("name"):
            missing_fields.append("patient_name")
        if not proposed_patient.get("phone"):
            missing_fields.append("patient_phone")
        if not proposed_patient.get("email"):
            missing_fields.append("patient_email")

        has_preferences = bool(
            proposed_preferences.get("date")
            and proposed_preferences.get("time_window")
        )

        available_slots = session.get("available_slots", [])
        selection = self._extract_slot_selection(message_text)

        metadata.setdefault("stub_state", "initial")
        date_error = metadata.get("preferred_date_error")
        if date_error and not proposed_preferences.get("date"):
            if date_error == "past_date":
                reply = (
                    "That date has already passed. Please share a future date in "
                    "YYYY-MM-DD format."
                )
            else:
                reply = (
                    "I need the appointment date in YYYY-MM-DD format, including "
                    "the year. Could you share it again?"
                )
            action = LLMAction(
                type="COLLECT_INFO",
                missing_fields=["preferred_date"],
            )
            return LLMResponse(
                reply_to_user=reply,
                action=action,
                extracted=extracted,
            )

        booking_error = metadata.get("booking_error")
        if booking_error == "missing_patient_email" or not proposed_patient.get(
            "email"
        ):
            reply = (
                "I need an email address to confirm your appointment. "
                "Could you please share it?"
            )
            action = LLMAction(
                type="COLLECT_INFO",
                missing_fields=["patient_email"],
            )
            return LLMResponse(
                reply_to_user=reply,
                action=action,
                extracted=extracted,
            )

        if selection is not None and available_slots:
            index = max(0, min(len(available_slots) - 1, selection))
            reply = (
                "Okay — sending your request to clinic. "
                "You’ll be notified when doctor confirms."
            )
            action = LLMAction(
                type="BOOK_SLOT",
                slot_index=index,
            )
            metadata["stub_state"] = "booking"
            return LLMResponse(
                reply_to_user=reply,
                action=action,
                extracted=extracted,
            )

        if available_slots and "slots_presented" not in metadata:
            slot_lines = [
                f"{idx + 1}) {slot['start_time']}"
                for idx, slot in enumerate(available_slots[:5])
            ]
            reply = (
                "I found these options: "
                + "; ".join(slot_lines)
                + ". Reply with the option number."
            )
            action = LLMAction(type="AWAIT_SLOT_SELECTION")
            metadata["slots_presented"] = True
            return LLMResponse(
                reply_to_user=reply,
                action=action,
                extracted=extracted,
            )

        if missing_fields:
            reply = (
                "Sure — may I have your "
                + " and ".join(missing_fields)
                + "?"
            )
            action = LLMAction(
                type="COLLECT_INFO",
                missing_fields=missing_fields,
            )
            metadata["stub_state"] = "collecting"
            return LLMResponse(
                reply_to_user=reply,
                action=action,
                extracted=extracted,
            )

        if not has_preferences:
            reply = (
                "Thanks. Could you share your preferred date "
                "(YYYY-MM-DD) and time window?"
            )
            action = LLMAction(
                type="COLLECT_INFO",
                missing_fields=["preferred_date", "preferred_time_window"],
            )
            metadata["stub_state"] = "collecting_preferences"
            return LLMResponse(
                reply_to_user=reply,
                action=action,
                extracted=extracted,
            )

        pref_date = proposed_preferences.get("date", "the requested date")
        pref_window = proposed_preferences.get(
            "time_window",
            "selected time",
        )
        reply = (
            "Thanks. I will check available slots for "
            f"{pref_date} in the {pref_window}."
        )
        action = LLMAction(type="CHECK_AVAILABILITY")
        metadata["stub_state"] = "checking"

        return LLMResponse(
            reply_to_user=reply,
            action=action,
            extracted=extracted,
        )

    def _extract_stub_fields(self, message_text: str) -> Dict[str, Any]:
        """Primitive entity extraction for the stub path."""

        if not message_text:
            return {}

        extracted: Dict[str, Any] = {}
        lowered = message_text.lower()

        comma_match = re.match(r"\s*([a-zA-Z][a-zA-Z\s]+),\s*(\+?\d[\d\s-]{6,})", message_text)
        if comma_match:
            extracted["patient_name"] = comma_match.group(1).strip().title()
            extracted["patient_phone"] = re.sub(r"\D", "", comma_match.group(2))

        name_match = re.search(r"(?:my name is|i am)\s+([a-zA-Z\s]+)", lowered)
        if name_match:
            extracted["patient_name"] = name_match.group(1).strip().title()

        phone_match = re.search(r"(\+?\d[\d\s-]{7,})", message_text)
        if phone_match:
            extracted["patient_phone"] = re.sub(r"\D", "", phone_match.group(1))

        email_match = re.search(r"[\w.%-]+@[\w.-]+", message_text)
        if email_match:
            extracted["patient_email"] = email_match.group(0)

        if "patient_name" not in extracted:
            if re.match(r"^[A-Za-z][A-Za-z\s]{2,40}$", message_text.strip()):
                extracted["patient_name"] = message_text.strip().title()

        date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", message_text)
        if date_match:
            extracted["preferred_date"] = date_match.group(1)

        if "morning" in lowered:
            extracted["preferred_time_window"] = "morning"
        elif "afternoon" in lowered:
            extracted["preferred_time_window"] = "afternoon"
        elif "evening" in lowered:
            extracted["preferred_time_window"] = "evening"

        return extracted

    @staticmethod
    def _extract_slot_selection(message_text: str) -> Optional[int]:
        """Translate numeric user replies into zero-based slot index."""

        if not message_text or not message_text.strip().isdigit():
            return None

        choice = int(message_text.strip())
        return max(0, choice - 1)
