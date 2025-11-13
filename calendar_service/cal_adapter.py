"""cal.com Calendar API adapter stub."""

from typing import Any, Dict, List


class CalComAdapter:
    """Stubbed adapter for interacting with cal.com API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def list_availability(self, event_type: str) -> List[Dict[str, Any]]:
        """Return mock availability slots from cal.com."""

        return []

    def book_appointment(
        self, event_type: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Stub booking call to cal.com."""

        return {
            "status": "pending",
            "event_type": event_type,
            "payload": payload,
        }
