# CONVERSATION.md

This document describes the conversation design, system prompt, action map, schema enforcement, fallback handlers, session memory guidance, and the test plan for RAAS (Rapid Automation Appointment Scheduler).

> **Usage:** Drop this file into `docs/CONVERSATION.md` in the repo. The test scaffold (pytest) is provided in `tests/test_conversation_flow.py`. These are **spec artifacts** for Codex / developers — adapt import paths in the test scaffold to match your code.

---

## 1. System prompt (Persona & Guardrails)

```
System: You are RAAS Assistant — the polite, concise, dental clinic receptionist for "Dentist Verma Clinic". 
Scope: Dentistry only (appointments, cancellations, questions about timings/availability, simple clinic policies). 
Tone: Professional, friendly, helpful, concise — like a human receptionist. 
Do not: provide medical advice, diagnose, offer treatment plans, take payments, or reveal system internals. 
Escalation: If user requests medical advice, billing disputes, or complex admin tasks, respond with a short safe-handoff and notify staff:
  "I can connect you with clinic staff for this. Would you like me to do that?"
Locale/timezone: Asia/Kolkata. Dates must be ISO (YYYY-MM-DD) in replies. Use local conventions consistently.
Output rule: Always respond in the required JSON schema; if you cannot, return {"error":"INVALID_JSON"}.
```

---

## 2. Action Map (canonical actions)

Each action below contains: trigger, required data, follow-up wording, validation & backend responsibility.

### COLLECT_INFO
- **Trigger:** Missing any required booking fields.
- **Required data:** `missing_fields` list.
- **Follow-up wording:** “May I have your <missing_field>?”
- **Validation:** phone → normalize/validate; date → parseable to ISO.
- **Backend:** Update session; re-invoke LLM when new information arrives.

### CHECK_AVAILABILITY
- **Trigger:** Required fields present or user asked to check.
- **Required data:** `preferred_date`, `preferred_time_window`, `dentist_id` (optional).
- **Follow-up wording:** “I will check available slots for <date> <time window> and get back with options.”
- **Backend:** Call `calendar_service.check_availability()`; store `available_slots`.

### AWAIT_SLOT_SELECTION
- **Trigger:** Backend returned candidate slots.
- **Required data:** cached `available_slots`.
- **Follow-up wording:** “I found N options: 1) … Reply with the option number.”
- **Validation:** present ≤ 5 options.

### BOOK_SLOT
- **Trigger:** User selects an option or asks to confirm.
- **Required data:** `slot_index`/`slot_id`, patient fields.
- **Follow-up wording:** “Okay — sending your request to clinic. You’ll be notified when doctor confirms.”
- **Backend:** Create cal.com host-confirmation booking; save Appointment `status=PENDING`; emit `appointment.requested`.

### CONFIRMATION_PROMPT
- **Trigger:** cal.com or backend confirms the booking.
- **Required data:** `calcom_booking_id`, final times.
- **Follow-up wording:** “Your appointment is confirmed for <date time> with Dr. X. Confirmation sent to <email/phone>.”
- **Backend:** Update Appointment → `CONFIRMED`; emit `appointment.confirmed`.

### SESSION_COMPLETE
- **Trigger:** Booking flow done or user cancels.
- **Follow-up wording:** “All done — would you like anything else?”
- **Backend:** Mark session closed; set TTL for cleanup.

### SMALL_TALK
- **Trigger:** Greetings / pleasantries.
- **Follow-up wording:** Short friendly reply and steer back to tasks.

---

## 3. LLM Response Schema (strict JSON)

Top-level object:

```json
{
  "reply_to_user": "string",
  "action": {
    "type": "string",
    "missing_fields": ["..."],
    "slot_index": 0,
    "slot_id": "string",
    "explain": "string"
  },
  "extracted": {
    "patient_name": "string",
    "patient_phone": "string",
    "patient_email": "string",
    "preferred_date": "YYYY-MM-DD or range",
    "preferred_time_window": "string",
    "dentist_id": "string",
    "reason": "string"
  }
}
```

**Rules:**
- `action.type` is mandatory.
- For `COLLECT_INFO`, `missing_fields` must be present.
- For `BOOK_SLOT`, `slot_index` or `slot_id` must reference cached slots.
- Backend must validate & normalize fields (phone, date).

---

## 4. Fallback & Repair Templates

- **Invalid JSON from LLM:**  
  Reply: “Sorry — temporary issue understanding my assistant. Can you rephrase? I'll connect you to staff if you prefer.”  
  Action: Retry LLM once, then escalate if still invalid.

- **Missing critical field:**  
  LLM should ask only for the missing field: “I need your mobile number to proceed. Please share it now.”

- **Ambiguous date/time:**  
  “Could you confirm the exact date? For example: 2025-11-15.”

- **Booking failed (slot gone):**  
  “Apologies — that slot is no longer available. Would you like the next available option within the same day or the next 2 days?”

- **Service error / rate limit:**  
  “I’m having trouble checking availability right now. Can I take your details and call you back, or try again in a minute?”

---

## 5. Session Memory Guidance

- Prompt includes:
  - `extracted` structured fields (always).
  - Last 2 assistant replies and last 3 user messages (condensed).
  - Up to 5 `available_slots` in short form.
- Token budget: keep prompt < 1500 tokens; drop oldest turns if needed.
- Log PII masked; prompts may contain patient name/phone but redact afterward in logs.
- Session TTL: 24 hours after `CLOSED`; retention policy configurable.

---

## 6. Testing & QA Plan (short)

- Unit: Validate LLM outputs against schema.
- Integration (sandbox):
  - Greeting → COLLECT_INFO → provide data → CHECK_AVAILABILITY (stubbed) → present slots → BOOK_SLOT (simulate cal.com pending) → expect Appointment `PENDING` in DB.
- Provide simulated webhook from cal.com to transition `PENDING` → `CONFIRMED` and ensure n8n event is fired.

---

## 7. Micro-step to implement (for Codex)

> Implement conversation control per this file: system prompt, action map, JSON schema validation, fallback handlers, and session memory guidance. Add a pytest integration test that simulates the full flow using a stubbed calendar_service and stubbed LLM response (file provided: `tests/test_conversation_flow.py`).

---

## 8. Notes for developers

- Keep the LLM's temperature low for deterministic action decisions.
- Always prefer small, explicit prompts with few-shot examples.
- Ensure separation of concerns: LLM decides; RAAS executes and persists.

