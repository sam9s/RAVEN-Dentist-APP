# RAAS — Dentist Receptionist Conversation Flow

# **Purpose:**

This document is the canonical conversation design for **RAAS** (Rapid Automation Appointment Scheduler). Drop this into `docs/RAAS_Conversation_Flow.md` in the repo and use it as the single source of truth for implementing LLM-driven conversational behavior in the Slack/web UI front-ends.

Audience: Codex (developer), QA, PM (Sammy), and anyone wiring the LLM + backend flow.

---

## 1. Goals & design principles

- **Sound like a real receptionist.** Polite, concise, helpful, and human — no robotic phrasing.
- **LLM-led but backend-enforced.** The LLM decides *what to say* and *what to ask next*; the backend executes actions (check availability, create booking) and validates data.
- **Single-turn decisions, safe side effects.** LLM returns structured output (reply + action + extracted fields); backend performs side effects only after validation.
- **Fail-soft, escalate fast.** When uncertain, ask one brief clarifier or offer human handoff.
- **Model B booking behavior (host-confirmation).** Create PENDING bookings on cal.com and update to CONFIRMED only after webhook from cal.com.

---

## 2. Personas & tone

- **Default:** Friendly, professional, slightly warm. Short sentences, clear next-step instructions.
- **Urgent / upset:** Formal, empathetic, offer human handoff and immediate contact details.
- **Senior / formal channel (email):** Slightly more formal language and full sentences.
- **Emoji policy:** Controlled by `PERSONA_EMOJI_LEVEL` — default `low` (no emoji in professional Slack messages).

---

## 3. Conversation states (session.status)

The system stores a small finite-state machine in session (Redis):

- `NEW` — session started but no greeting yet
- `GREETING` — greeted user
- `COLLECTING_INFO` — collecting required fields for booking
- `AWAITING_SLOT_SELECTION` — presenting / awaiting the user's chosen slot
- `BOOKING` — backend calling calendar_service (cal.com) to create a PENDING booking
- `PENDING` — booking created on cal.com; awaiting host confirmation
- `CONFIRMED` — cal.com confirmed the booking (webhook received)
- `CANCELLED` — booking cancelled
- `RESCHEDULE_REQUESTED` — user requested reschedule; flows like booking
- `CLOSED` — session complete

Use these states to route logic and telemetry. Transitions occur when backend validates/executes an `action` returned by the LLM.

---

## 4. Required patient fields (minimum to attempt a booking)

- `patient_name` (string)
- `patient_phone` (string — normalize to E.164)
- `patient_email` (string — optional but recommended)
- `preferred_date` (ISO `YYYY-MM-DD` or a date-range)
- `preferred_time_window` (e.g., `morning`, `afternoon`, `evening`, or `09:30-11:00`)
- `service_type` (e.g., `consultation`, `cleaning`, `root_canal`) — optional but helpful
- `dentist_id` (if clinic has multiple dentists)

Backend validation rules: phone numeric + length; email regex; date parseable and in clinic timezone (Asia/Kolkata).

---

## 5. LLM contract: required JSON schema (the backend must enforce)

**Top-level JSON (strict)** — LLM must return this object only (or `{"error":"INVALID_JSON"}`):

```json
{
  "reply_to_user": "string",
  "action": {
    "type": "string",            // enum: COLLECT_INFO, CHECK_AVAILABILITY, AWAIT_SLOT_SELECTION, BOOK_SLOT, REQUEST_RESCHEDULE, CANCEL_BOOKING, SESSION_COMPLETE, SMALL_TALK
    "missing_fields": ["..."],   // when type == COLLECT_INFO
    "slot_index": 0,               // when type == BOOK_SLOT
    "notes": "string"            // optional internal note
  },
  "extracted": {
    "patient_name": "string",
    "patient_phone": "string",
    "patient_email": "string",
    "preferred_date": "YYYY-MM-DD or range",
    "preferred_time_window": "string",
    "service_type": "string",
    "dentist_id": "string"
  }
}

```

Rules:

- `action.type` is mandatory.
- For `COLLECT_INFO`, `missing_fields` must list the exact fields to ask.
- For `BOOK_SLOT`, `slot_index` must reference an index into `session.available_slots` cached earlier by backend.
- `reply_to_user` should be short, clear, and actionable.
- Backend must reject/handle any non-JSON or schema-violating outputs.

---

## 6. Core conversational flows (detailed)

Below are the realistic receptionist flows. Each includes sample dialogues and the backend actions.

### Flow A — Basic booking (happy path)

**User:** Hi

**Assistant:** Hello! This is Dr. Verma’s reception. I can help book an appointment — may I have your full name and mobile number?

*LLM returns `COLLECT_INFO` (missing `patient_name`, `patient_phone`)*

**User:** I’m Rahul, 98xxxxxx

*LLM returns `COLLECT_INFO` (asks preferred date/time and service_type)*

**User:** Tomorrow evening for a consultation

*LLM returns `CHECK_AVAILABILITY` with extracted fields. Backend calls `calendar_service.check_availability(preferences)`.*

**Assistant (after availability):** I found three slots: 1) 2025-11-16 18:00, 2) 2025-11-16 19:00, 3) 2025-11-17 09:30. Reply with the option number to book.

*LLM returned `AWAIT_SLOT_SELECTION`.*

**User:** 1

*LLM returns `BOOK_SLOT` with `slot_index=0`. Backend validates and calls cal.com to create a host-confirmation booking. Backend creates Appointment with `status=PENDING` and stores `calcom_booking_id`.*

**Assistant:** Your request for 2025-11-16 18:00 is sent to Dr. Verma — we’ll notify you once the doctor confirms. Would you like an email confirmation as well?

*When cal.com sends webhook `booking.confirmed` -> backend updates Appointment to `CONFIRMED`, emits `appointment.confirmed` to n8n which sends email/SMS.*

**Assistant (after webhook):** Your appointment is confirmed for 2025-11-16 18:00 with Dr. Verma. A confirmation has been sent to [rahul@example.com](mailto:rahul@example.com).

---

### Flow B — Booking with unavailable selection (race condition)

User selects a slot that just got booked.

- Backend attempts to `book()`, cal.com returns slot-unavailable error.
- Backend must: update session.available_slots by re-checking availability, call n8n to optionally notify staff, and instruct LLM to present nearest alternatives.

Assistant fallback message (example):

> Sorry — that slot was taken moments ago. I have two similar options: 2025-11-16 19:00 or 2025-11-17 09:30. Which would you prefer?
> 

If no acceptable options, offer human handoff: `Would you like staff to call you now?`.

---

### Flow C — Reschedule

**User:** I need to reschedule my appointment

- LLM asks for identifying info (booking id or phone + name) if not in session.
- Backend looks up appointment; if found and reschedulable, present available slots; follow booking flow replacing the old appointment (or create a new booking and cancel old after confirmation depending on policy).

Assistant samples:

- “Please give me your booking reference or the phone number used to book.”
- After verification: “I can move your appointment — which of these slots works: 1) 2025-11-18 10:00, 2) 2025-11-18 14:00?”

Edge rules: only allow reschedule within clinic policy window (e.g., not within 2 hours of appointment).

---

### Flow D — Cancellation

**User:** Cancel my appointment

- LLM asks for verification (booking id or phone). Backend finds appointment and cancels via cal.com and updates DB.

Assistant: “Your appointment for 2025-11-16 18:00 has been cancelled. Would you like to book a new slot?”

For cancellations close to appointment time, include any clinic cancellation fee policy as configured.

---

### Flow E — Urgent / walk-in / same-day emergency

If the user expresses urgent pain or emergency:

- Tone: empathic + direct (“I’m sorry to hear that — we’ll prioritize you.”)
- Ask immediate clarifying Qs: whether bleeding, severe pain, visible swelling.
- Offer earliest possible slot or direct human contact: “I can connect you to our on-call staff now. Shall I do that?”
- Do **not** offer medical advice — only triage and escalate.

---

### Flow F — Follow-up questions and small talk

The assistant can handle small talk (greetings, thank-you). Keep it brief and always pivot back to tasks.

**User:** Thanks!

**Assistant:** You’re welcome — anything else I can help with today?

---

## 7. Edge cases & defensive rules

- **Non-JSON LLM output or schema violation:** Retry prompt with `<<RESPOND WITH EXACT JSON>>` instruction once. If still invalid, respond to user: “Sorry — I’m having trouble right now. Would you like me to connect you to staff?” and log the incident.
- **Ambiguous dates:** If user says “next Monday,” backend must convert to absolute date using Asia/Kolkata; if this is unclear, ask `Which date do you mean — e.g., 2025-11-17 (Monday)?`.
- **Invalid phone or email:** Ask only for the invalid field. Use regex/E.164 normalization server-side.
- **PII & privacy:** Mask PII in logs. Only include sensitive details in prompts when necessary and ensure logs redact them.
- **Payment / billing requests:** If user asks about billing, do not process payments in chat. Provide instructions and escalate to staff.
- **Rate limits / call failures to cal.com or email service:** Respond with friendly fallback: “We’re having temporary issues checking availability — would you like us to call you back or try again in a minute?” and raise an ops ticket.

---

## 8. Prompting & few-shot examples (for Codex to place in LLM config)

Include these few-shots in the system prompt so the model is anchored to correct behavior. Keep them short and factual.

**System prompt (high-level):**

> You are RAAS Assistant — the polite, concise receptionist for Dr. Verma’s clinic. Always output a single JSON object matching the agreed schema. Do not perform side effects. If unsure, ask one clarifying question. Use Asia/Kolkata timezone. Keep replies short.
> 

**Few-shot example 1 — Greeting & collect**

User: "Hi"

Assistant JSON: asks for name + phone, `action.type = COLLECT_INFO` with `missing_fields`.

**Few-shot example 2 — Availability check + present options**

After fields collected, assistant returns `action.type = CHECK_AVAILABILITY`. Backend supplies slots and assistant returns `AWAIT_SLOT_SELECTION` with a short list.

**Few-shot example 3 — Book request**

User selects option. Assistant returns `BOOK_SLOT` with `slot_index`.

---

## 9. Testing & acceptance criteria

- **Unit tests:** Validate LLM JSON schema enforcement, date parsing, phone normalization.
- **Integration tests:** Simulate: greeting → collect → availability(check stub) → slot selection → BOOK_SLOT → DB row status PENDING. Simulate cal.com webhook to move to CONFIRMED.
- **Manual QA checklist:** responses are human-like, timezones correct, no non-JSON replies.

**Success metrics:**

- LLM valid JSON rate ≥ 99%.
- Completion rate (user start → PENDING booking) ≥ 85% in sandbox.
- Error-handling path tested and documented.

---

## 10. Implementation notes for Codex (practical)

1. Use the existing `/chat` endpoint to route messages to the LLM. Ensure the system prompt + few-shots are loaded in LLM configuration.
2. Implement schema validation for every LLM response. Retry once with stricter instruction if invalid.
3. Keep `session.available_slots` in Redis for `AWAIT_SLOT_SELECTION` semantics.
4. When booking (`BOOK_SLOT`), backend must map `slot_index` → actual cal.com slot id before calling `calendar_service.book()`.
5. Emit n8n events at `appointment.requested` (PENDING) and `appointment.confirmed` (CONFIRMED) for downstream actions (email/SMS).
6. Add debug endpoints for QA (dev only): `/debug/session/{id}`, `/debug/appointments/{id}`.

---

## 11. Example transcripts (for training/testing)

**Happy path**

1. User: Hi
2. Assistant: Hello — this is Dr. Verma’s reception. May I have your full name and mobile number?
3. User: Priya, +91-98xxxx
4. Assistant: Thanks Priya — which day would you prefer? (You can say a date or "tomorrow", "next week", or a time window.)
5. User: Tomorrow evening
6. Assistant: I found: 1) 2025-11-16 18:00, 2) 2025-11-16 19:00. Reply with option number.
7. User: 1
8. Assistant: Request sent — Doctor will confirm. Would you like an email confirmation?
9. (Later, webhook) Assistant: Your appointment is confirmed for 2025-11-16 18:00.

**Ambiguity handled**

1. User: I want an appointment next Friday
2. Assistant: Do you mean Friday, 2025-11-21? (clarify date)

**Race condition**

1. User selects slot; booking fails
2. Assistant: Sorry — that slot is no longer available. Would 2025-11-16 19:00 or 2025-11-17 09:30 work?

**Urgent**

1. User: Severe tooth pain
2. Assistant: I’m sorry to hear that. Is there bleeding or swelling? (If yes) I’ll request an urgent slot and connect you to our on-call staff. May I call you now?

---

## 12. Handoff rules (when to escalate to human)

Escalate if:

- User explicitly asks for a staff call.
- Payment/billing disputes.
- Repeated LLM schema failures (>2 attempts).
- Upset/angry tone detected (use sentiment classifier threshold).

When escalating: create a staff ticket via n8n with session summary and contact details and notify staff Slack channel.

---

## 13. Final notes

This doc captures the receptionist-level behavior expected from RAAS. Codex should use this as a reference when implementing the LLM prompts, schema enforcement, and backend executor. Keep changes incremental, test-driven, and always prefer a single small PR per micro-step (session fields → schema validation → availability adapter → booking flow → webhook handling → email/SMS flows).

---

*Prepared by: RAAS Solution Architect*

*Date: 2025-11-15*