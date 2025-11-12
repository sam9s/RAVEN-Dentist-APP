"""Google Calendar API adapter stub."""

from typing import Any, Dict, List


class GoogleCalendarAdapter:
    """Stubbed adapter for interacting with Google Calendar API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def list_availability(self, calendar_id: str) -> List[Dict[str, Any]]:
        """Return mock availability slots for a calendar."""

        return []

    def book_appointment(self, calendar_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Stub booking call to Google Calendar."""

        return {"status": "pending", "calendar_id": calendar_id, "payload": payload}
