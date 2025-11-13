# RAAS – Design Brief for Codex (READ THIS BEFORE CODING)

## 1. Overview

RAAS (**Rapid Automation Appointment Scheduler**) is a conversational AI dentist appointment scheduler under the RAVEN multiverse.

It must:

- Talk to users on **Slack** and a simple **Web UI** (later WhatsApp).
- Hold a **natural, human-like conversation** using **OpenAI** APIs.
- Collect:
  - Patient details (name, phone, email),
  - Appointment preferences (date, time window, dentist/clinic, reason).
- Check **availability via cal.com**.
- Book appointments on cal.com.
- Persist data in **Postgres** (Patients, Dentists, Appointments).
- Store session state in **Redis**.
- Emit events to **n8n** for:
  - Email confirmations,
  - Internal Slack notifications,
  - Future CRM integrations.

**Roles in this project:**

- `slack_bot/`  
  Existing Node Slack bot cloned from another RAVEN project. It acts as a **channel adapter** for Slack and forwards normalized events to RAAS via HTTP.

- `backend/`  
  FastAPI-based RAAS core service: conversation brain + business logic + integrations.

- `calendar_service/`  
  A **cal.com adapter**, not Google Calendar. It encapsulates all cal.com API calls.

- `orchestrator/`  
  n8n workflows and related assets.

- `infra/`  
  DB schema, Alembic migrations, `.env`, and other infra configs.

---

## 2. Component Responsibilities & Boundaries

### 2.1 Slack_bot (existing)

- Handles Slack app setup, slash commands, events, and signatures.
- For RAAS, it forwards messages to RAAS via a single HTTP endpoint, e.g.:

  ```json
  {
    "session_id": "<unique-per-user-conversation>",
    "channel": "slack",
    "user_id": "<slack-user-id>",
    "message_text": "<what the user typed or selected>"
  }
  ```

- It displays whatever `reply_to_user` RAAS returns.

### 2.2 Web UI

- Simple front-end (for now) that also sends `POST /chat` with the same payload shape.
- Generates its own `session_id` (UUID) per browser session.

### 2.3 RAAS Backend (FastAPI)

**Single conversation entrypoint:**

- `POST /chat`  
  Input: `{session_id, channel, user_id, message_text}`.

Responsibilities:

1. Load or create **session** from Redis.
2. Call **OpenAI LLM** with:
   - System prompt (RAAS persona + rules),
   - Conversation context from Redis,
   - Latest user message,
   - Clear instruction to output a strict JSON schema.
3. Parse LLM response into:
   - `reply_to_user` (string),
   - `action` (what to do),
   - `extracted` (structured data).
4. Execute business logic based on `action`:
   - Check availability via `calendar_service` (cal.com),
   - Book appointment via `calendar_service`,
   - Read/write **Postgres**,
   - Emit webhooks to **n8n**.
5. Update session in Redis.
6. Return `reply_to_user` to Slack_bot/Web.

**Other endpoints (MVP):**

- `GET /health` – return basic service health (OK / version).

Future:

- Webhook endpoint for cal.com events (`/webhooks/calcom`) – can be stubbed for now.

### 2.4 Calendar Service (cal.com adapter)

- Lives under `calendar_service/`.
- RAAS must **not** call cal.com directly. All cal.com calls go through here.

Responsibilities:

- `check_availability(preferences)`  
  Input: canonical preferences (date, time window, dentist/clinic).  
  Output: list of **normalized slots** with fields like:
  - `slot_id`
  - `start_time` (ISO)
  - `end_time` (ISO)
  - `dentist_id` (internal or cal.com mapping)

- `book_appointment(appointment_data)`  
  Input: canonical appointment payload (patient, slot, reason, etc.).  
  Output: booking confirmation with:
  - `calcom_booking_id`
  - confirmed `start_time`, `end_time`
  - any booking URLs returned by cal.com.

### 2.5 Postgres (business records)

Tables needed for v1:

- **Patient**
- **Dentist**
- **Appointment**

(Fields defined in section 4.)

### 2.6 Redis (session state)

- Stores **conversation sessions** keyed by `session_id`.
- Used for:
  - Conversation status,
  - Extracted patient + preference data,
  - Cached available slots,
  - Minimal conversation history for LLM context.

(Session model in section 3.)

### 2.7 n8n (orchestrator)

- RAAS emits webhooks to n8n on key events, especially:

  - `appointment.booked`

- n8n workflow responsibilities:

  - Send **email confirmation** to patient.
  - Send **internal Slack message** to a staff channel (e.g. `#clinic-bookings`).
  - Future: CRM update, reminders, etc.

RAAS should remain unaware of email/CRM specifics; it just sends clean webhook payloads to n8n.

---

## 3. Conversation & LLM Contract

### 3.1 Message Flow

For every user message:

1. Channel → `slack_bot` / Web → `POST /chat` on RAAS.
2. RAAS:
   - Loads session from Redis (or creates a new one).
   - Calls OpenAI LLM with system + context + latest user message.
   - Receives a **JSON response**.
   - Updates session and executes any actions (calendar, DB, n8n).
   - Returns `reply_to_user` to the channel.

The LLM is **not allowed** to call any external systems directly.  
It only chooses what RAAS should do next via an `action` object.

### 3.2 LLM Response Schema

Every LLM response must be a single JSON object with keys:

- `reply_to_user`: string  
  The natural-language reply that Slack/Web should show to the user.

- `action`: object  
  Required key: `type` – an enum string, one of:

  - `COLLECT_INFO`  
    → Ask user for missing information.

  - `CHECK_AVAILABILITY`  
    → RAAS should call `calendar_service.check_availability()`.

  - `AWAIT_SLOT_SELECTION`  
    → RAAS already presented options; now waiting for a slot choice.

  - `BOOK_SLOT`  
    → RAAS should call `calendar_service.book_appointment()` using a chosen slot.

  - `SESSION_COMPLETE`  
    → Conversation flow is done; RAAS should mark session as complete.

  Optional keys depending on `type`:

  - For `COLLECT_INFO`:
    - `missing_fields`: array of strings (e.g. `["patient_name", "patient_phone"]`)
  - For `BOOK_SLOT`:
    - `slot_index` (integer) or `slot_id` (string) referencing one of the cached slots in the session.

- `extracted`: object  
  Structured data the LLM has inferred or confirmed from user messages. Fields may include:

  - `patient_name`
  - `patient_phone`
  - `patient_email`
  - `preferred_date` (ISO date string)
  - `preferred_time_window` (e.g. `"morning"`, `"afternoon"`, `"evening"`, or `"15:00–18:00"`)
  - `dentist_id` or `dentist_name` (where applicable)
  - `reason` (free text, e.g. `"tooth pain"`)

**RAAS logic:**

- Merge `extracted` into the Redis session on every turn.
- Use `action.type` to decide which business operation(s) to perform.
- Never trust the model for direct side effects; always execute side effects (DB, cal.com, n8n) in RAAS code.

---

## 4. Minimal Data Model (Postgres – conceptual)

ORM details are up to implementation, but v1 needs these fields:

### 4.1 Patient

- `id`
- `name`
- `phone`
- `email`
- `created_at`

(Optionally `external_id` for future CRM, not required for MVP.)

### 4.2 Dentist

- `id`
- `name`
- `clinic_name`
- `calcom_calendar_id` (or whatever identifier cal.com uses for this dentist/clinic)
- `is_active`
- `created_at`

### 4.3 Appointment

- `id`
- `patient_id` (FK → Patient)
- `dentist_id` (FK → Dentist)
- `calcom_booking_id`
- `start_time`
- `end_time`
- `status` (e.g. `PENDING`, `CONFIRMED`, `CANCELLED`)
- `channel` (e.g. `slack`, `web`)
- `reason` (text)
- `created_at`
- `updated_at`

MVP assumption:  
RAAS will always attempt to keep Postgres and cal.com in sync. cal.com is the **calendar source of truth**, Postgres is the **business/analytics source of truth**.

---

## 5. Redis Session Model (Conceptual)

Key pattern example:

- `raas:session:{session_id}`

Stored structure conceptually contains:

- `status`
  - e.g. `collecting_info`, `awaiting_slot_choice`, `booking_confirmed`

- `patient`
  - `name`
  - `phone`
  - `email`

- `preferences`
  - `preferred_date`
  - `preferred_time_window`
  - `dentist_id`
  - `reason`

- `available_slots`
  - List of slots returned by `calendar_service.check_availability()`
  - Each slot:
    - `slot_id`
    - `start_time`
    - `end_time`
    - `dentist_id`
    - Any other cal.com-specific context needed for booking

- `history`
  - Short conversation history used for LLM context (e.g. limited number of recent turns).

Implementation details (serialization, expiry) are flexible as long as this conceptual information is maintained.

---

## 6. API Surface & Phase 1 Implementation Scope

### 6.1 Required Endpoints (MVP)

1. `POST /chat`  
   Input: `{session_id, channel, user_id, message_text}`.

   Behaviour:

   - Load/create session in Redis.
   - Call OpenAI (LLM) with system prompt + context.
   - Parse `reply_to_user`, `action`, `extracted`.
   - Merge `extracted` into session.
   - Depending on `action.type`:
     - `COLLECT_INFO`:
       - Just update session and return `reply_to_user`.
     - `CHECK_AVAILABILITY`:
       - Call `calendar_service.check_availability()` with preferences from session.
       - Store returned `available_slots` in session.
       - Optionally call LLM again to phrase choices, then return the phrased `reply_to_user`.
     - `AWAIT_SLOT_SELECTION`:
       - Just update status; wait for next user message.
     - `BOOK_SLOT`:
       - Use slot from `available_slots` (by `slot_index`/`slot_id`).
       - Call `calendar_service.book_appointment()`.
       - Create Patient and Appointment rows in Postgres.
       - Emit `appointment.booked` event to n8n (HTTP webhook).
       - Optionally call LLM again to phrase confirmation.
     - `SESSION_COMPLETE`:
       - Mark session complete and set TTL/cleanup in Redis.
   - Always return `{reply_to_user}` for Slack/Web to display.

2. `GET /health`  
   Simple health check of RAAS (and optionally DB/Redis connectivity).

(Other endpoints like cal.com webhooks can be added later; not required for the first working slice.)

### 6.2 Phase 1 Vertical Slice – What to Implement First

For the **first working version**, implement:

1. `POST /chat` with:
   - Redis session handling,
   - LLM integration using the response schema described above,
   - Support for `COLLECT_INFO`, `CHECK_AVAILABILITY`, `BOOK_SLOT`, `SESSION_COMPLETE` paths.

2. Basic `calendar_service`:
   - Real cal.com integration if credentials are available, or a thin adapter ready to plug in.
   - Enough to:
     - Query a single dentist’s availability for a given date/time window.
     - Book a slot and return booking details.

3. Postgres models + Alembic migrations:
   - Patient, Dentist, Appointment as defined above.

4. n8n integration:
   - On successful booking, send an `appointment.booked` webhook to n8n with:
     - `appointment_id`
     - patient data
     - schedule
     - channel
     - `calcom_booking_id`

5. Minimal logging and error handling:
   - Clear logs for:
     - LLM requests/responses (redact sensitive data as needed),
     - cal.com calls,
     - DB writes,
     - n8n webhooks.

---

**Instruction to Codex:**

- Do **not** change this architecture or contract.
- Use this document as the functional spec.
- Implement the Phase 1 vertical slice described in section 6.2.
- Keep the code modular and aligned with the existing folder structure (`backend/`, `calendar_service/`, `infra/`, etc.).
