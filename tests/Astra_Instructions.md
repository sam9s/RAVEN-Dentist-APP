TL;DR (what’s wrong)

Cal.com expects a responses object (not an array) that contains booking-field keys (slugs) mapped to values — including the default name and email fields.

Your current payload either omits responses or sends it as an empty object/array — Cal returns:
invalid_type in 'responses,email': Required; invalid_type in 'responses,name': Required
→ so Cal requires responses.email and responses.name.

Exact instructions to give Codex (copy-paste)

Confirm API version and endpoint

Check which endpoint code calls: /v1/bookings or /v2/bookings. Use the same example below but replace v1/v2 consistently in the code and tests.

Fetch event-type booking fields (optional but ideal)

Before booking, call:

GET https://api.cal.com/v1/event-types/<EVENT_TYPE_ID>


Inspect bookingFields (if any) and note each field’s slug. Use those slugs as keys in responses. If there are no custom bookingFields, use the defaults name and email.

This makes the adapter robust for custom forms.

Construct the booking payload exactly like this
Use this JSON for the POST to /v1/bookings (adjust for /v2 if you use v2):

{
  "eventTypeId": 3902598,
  "start": "2025-11-18T10:00:00+05:30",
  "end":   "2025-11-18T10:30:00+05:30",
  "attendees": [
    {
      "name": "Sammy",
      "email": "sam9s@outlook.com",
      "timeZone": "Asia/Kolkata",
      "language": "en"
    }
  ],
  "timeZone": "Asia/Kolkata",
  "language": "en",
  "responses": {
    "name": "Sammy",
    "email": "sam9s@outlook.com",
    "phoneNumber": "+919810877012"     // optional, include if your event has phoneNumber field
  }
}


Important notes:

responses must be an object; keys must be the booking field slugs (for default fields use name and email).

attendees array is OK to include; responses provides the booking form answers that Cal validates.

If the event has custom booking field slugs (e.g., patient_phone, patient_name), use those exact slugs instead of phoneNumber or name.

If your adapter currently sends responses: {} or responses: [] — change it to the object above.

Add defensive logic (small code changes):

If bookingFields exist, map collected user answers to those field slugs. Pseudocode:

if booking_fields: 
    responses = { field.slug: session_data.get(local_key_for_field) for field in booking_fields }
else:
    responses = {"name": session.patient_name, "email": session.patient_email}


Ensure responses is serialized as a JSON object (dict), not a JSON array.

Instrument debug logging (temporary)
Surround the booking call with logs showing the exact request JSON you send (redact API key), and log the full response body on failure. Example:

logger.debug("CAL BOOKING REQ: %s", json.dumps(payload))
logger.debug("CAL BOOKING RESP: %s %s", resp.status_code, resp.text)


Run the server test & paste outputs

Run the existing tools/cal_test.py or make a small POST test that sends the exact booking payload above to /v1/bookings from the same machine as the server.

If the booking fails, paste the full response body here (we need the error details).

Quick sanity checks Codex must run now

Confirm responses is an object and contains at least name and email.

Confirm the event’s minimumBookingNotice (120 minutes) — your chosen start must be at least 2 hours in future. If too close, Cal may reject. Test with a date/time comfortably > 2 hours ahead.

Confirm timezone format (e.g., Asia/Kolkata) in timeZone field.

Confirm attendees entries include email and name (some Cal versions require both in attendees and responses).

Example full POST (copy-pasteable curl for Codex to test locally)
curl -X POST "https://api.cal.com/v1/bookings" \
  -H "Authorization: Bearer <CAL_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "eventTypeId": 3902598,
    "start": "2025-11-18T10:00:00+05:30",
    "end": "2025-11-18T10:30:00+05:30",
    "attendees":[{"name":"Sammy","email":"sam9s@outlook.com","timeZone":"Asia/Kolkata","language":"en"}],
    "timeZone":"Asia/Kolkata",
    "language":"en",
    "responses": {"name":"Sammy","email":"sam9s@outlook.com","phoneNumber":"+919810877012"}
  }'


If this succeeds in curl/Postman but the server call still fails, it proves the server is sending a malformed responses (wrong type or wrong keys) — check the server’s debug-logged payload.

What you (PM) should ask Codex to paste here

When Codex runs the test, have them paste:

The exact booking payload the backend sends (the logged JSON).

The Cal.com response body (the full JSON) and status code.

The GET /v1/event-types/<id> response snippet showing bookingFields if present.

If they changed any code, the small commit/PR hash.

Paste those here and I’ll read them and instruct the exact one-line fix if needed.