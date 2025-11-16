# cal_test.py
import os, requests, json
from dotenv import load_dotenv

load_dotenv(".env")
API_KEY = os.environ.get("CAL_API_KEY")
BASE = "https://api.cal.com/v1"

def show(k,v):
    print(f"--- {k} ---")
    print(v if isinstance(v,str) else json.dumps(v, indent=2))

headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type":"application/json","Accept":"application/json"}

# 1) list event-types (sanity)
r = requests.get(f"{BASE}/event-types", headers=headers, timeout=10)
show("event-types status", r.status_code)
show("event-types body", r.text)

# 2) attempt availability check (mimic what backend should do)
# Adjust payload per what your backend would send; this is a reasonable guess:
payload = {
  "eventTypeId": int(os.environ.get("CAL_EVENT_TYPE_ID") or 0),
  "timezone": os.environ.get("CAL_TIMEZONE") or "Asia/Kolkata",
  "startDate": "2025-11-16",
  "endDate":   "2025-11-18"
}
r2 = requests.post(f"{BASE}/availability/time-slots", headers=headers, json=payload, timeout=10)
show("availability status", r2.status_code)
show("availability body", r2.text)

# 3) try to create a booking (simulated)
payload3 = {
  "eventTypeId": int(os.environ.get("CAL_EVENT_TYPE_ID") or 0),
  "start": "2025-11-18T10:00:00+05:30",
  "end":   "2025-11-18T10:30:00+05:30",
  "attendees":[{"email":"test@example.com", "name":"Sam"}]
}
r3 = requests.post(f"{BASE}/bookings", headers=headers, json=payload3, timeout=10)
show("booking status", r3.status_code)
show("booking body", r3.text)
