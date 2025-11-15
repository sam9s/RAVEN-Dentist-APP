# tests/test_conversation_flow.py
#
# Integration-style happy-path test for RAAS receptionist flow. The test:
#   * Calls FastAPI app (backend.main:app) through httpx.AsyncClient.
#   * Replaces Redis cache helpers with an in-memory dict.
#   * Stubs RAASLLMClient.generate_response to emit a scripted sequence.
#   * Stubs calendar_service adapter methods to avoid live API calls.
#
# Update `import_path_app` if the FastAPI app entry point moves.

import json
from typing import Any, Dict, List

import pytest
from httpx import ASGITransport, AsyncClient

# === CONFIGURE THESE to match your project ===
import_path_app = "backend.main:app"


# === helpers ===

async def import_app():
    module_name, app_name = import_path_app.split(":")
    mod = __import__(module_name, fromlist=[app_name])
    return getattr(mod, app_name)

@pytest.mark.anyio
async def test_conversation_happy_path(monkeypatch):
    # import app
    app = await import_app()

    # monkeypatch in-memory cache for sessions to avoid Redis dependency
    import backend.services.session as session_mod

    cache_store: Dict[str, str] = {}

    def fake_cache_set(key: str, value: str, ex: int | None = None) -> bool:
        cache_store[key] = value
        return True

    def fake_cache_get(key: str) -> str | None:
        return cache_store.get(key)

    monkeypatch.setattr(session_mod, "cache_set", fake_cache_set)
    monkeypatch.setattr(session_mod, "cache_get", fake_cache_get)

    # monkeypatch LLM client generate_response with deterministic sequence
    from backend.services.llm import LLMAction, LLMResponse, RAASLLMClient

    responses: List[LLMResponse] = [
        LLMResponse(
            reply_to_user=(
                "Hello — this is Dentist Verma’s reception. "
                "May I have your full name and mobile number?"
            ),
            action=LLMAction(
                type="COLLECT_INFO",
                missing_fields=["patient_name", "patient_phone"],
            ),
            extracted={},
        ),
        LLMResponse(
            reply_to_user="Thanks. I will check available slots for 2025-11-15 in the evening.",
            action=LLMAction(type="CHECK_AVAILABILITY"),
            extracted={
                "patient_name": "Test User",
                "patient_phone": "9999999999",
                "preferred_date": "2025-11-15",
                "preferred_time_window": "evening",
                "service_type": "consultation",
            },
        ),
        LLMResponse(
            reply_to_user=(
                "I found two options: 1) 2025-11-15 18:00, 2) 2025-11-15 19:00. "
                "Reply with the option number."
            ),
            action=LLMAction(type="AWAIT_SLOT_SELECTION"),
            extracted={},
        ),
        LLMResponse(
            reply_to_user=(
                "Okay — sending your request to clinic. You’ll be notified when "
                "doctor confirms."
            ),
            action=LLMAction(type="BOOK_SLOT", slot_index=0, notes="patient selected option 1"),
            extracted={},
        ),
    ]

    call_index = {"value": 0}

    def fake_generate_response(
        self: RAASLLMClient,
        *,
        session: Dict[str, Any],
        message_text: str,
        channel: str,
    ) -> LLMResponse:
        idx = call_index["value"]
        call_index["value"] = min(len(responses) - 1, idx + 1)
        return responses[idx]

    monkeypatch.setattr(
        RAASLLMClient,
        "generate_response",
        fake_generate_response,
    )

    # monkeypatch calendar adapter used by chat router
    import backend.routers.chat as chat_router

    def fake_check_availability(preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "slot_id": "s1",
                "start_time": "2025-11-15T18:00:00+05:30",
                "end_time": "2025-11-15T18:30:00+05:30",
                "dentist_id": "d1",
            },
            {
                "slot_id": "s2",
                "start_time": "2025-11-15T19:00:00+05:30",
                "end_time": "2025-11-15T19:30:00+05:30",
                "dentist_id": "d1",
            },
        ]

    def fake_book_appointment(*, slot: Dict[str, Any], patient: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "calcom_booking_id": "cal_123",
            "status": "PENDING",
            "start_time": slot["start_time"],
            "end_time": slot["end_time"],
            "patient_name": patient.get("name"),
        }

    monkeypatch.setattr(chat_router, "calendar_client", chat_router.calendar_client)
    monkeypatch.setattr(
        chat_router.calendar_client,
        "check_availability",
        fake_check_availability,
    )
    monkeypatch.setattr(
        chat_router.calendar_client,
        "book_appointment",
        fake_book_appointment,
    )

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        # Step 1: greeting
        resp = await ac.post("/chat", json={"session_id": "s1", "channel": "slack", "user_id": "u1", "message_text": "Hi"})
        assert resp.status_code == 200
        body = resp.json()
        assert "reply_to_user" in body

        # Step 2: user supplies name & phone & date/time
        resp = await ac.post("/chat", json={"session_id": "s1", "channel": "slack", "user_id": "u1", "message_text": "My name is Test User, phone 9999999999, I want 2025-11-15 evening."})
        assert resp.status_code == 200
        body = resp.json()
        assert "reply_to_user" in body

        # Step 3: simulate backend added slots and LLM presents options
        resp = await ac.post("/chat", json={"session_id": "s1", "channel": "slack", "user_id": "u1", "message_text": "Please show options"})
        assert resp.status_code == 200
        body = resp.json()
        assert "reply_to_user" in body

        # Step 4: user selects option 1
        resp = await ac.post("/chat", json={"session_id": "s1", "channel": "slack", "user_id": "u1", "message_text": "1"})
        assert resp.status_code == 200
        body = resp.json()
        assert "reply_to_user" in body

        # session metadata should include booking stub result
        stored_state = json.loads(cache_store["raas:session:s1"])
        assert stored_state["metadata"].get("latest_booking", {}).get("status") == "PENDING"
