"""cal.com Calendar API adapter stub."""

from __future__ import annotations

from typing import Any, Dict, List


class CalComAdapter:
    """Stubbed adapter for interacting with cal.com API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def check_availability(
        self, preferences: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Return mock availability slots from cal.com."""

        preferred_date = preferences.get("date", "2025-11-15")
        dentist_id = preferences.get("dentist_id", "dr_verma")

        return [
            {
                "slot_id": f"{preferred_date}-18",
                "start_time": f"{preferred_date}T18:00:00+05:30",
                "end_time": f"{preferred_date}T18:30:00+05:30",
                "dentist_id": dentist_id,
            },
            {
                "slot_id": f"{preferred_date}-19",
                "start_time": f"{preferred_date}T19:00:00+05:30",
                "end_time": f"{preferred_date}T19:30:00+05:30",
                "dentist_id": dentist_id,
            },
        ]

    def book_appointment(
        self, *, slot: Dict[str, Any], patient: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Stub booking call to cal.com."""

        return {
            "calcom_booking_id": f"booking-{slot['slot_id']}",
            "status": "PENDING",
            "start_time": slot.get("start_time"),
            "end_time": slot.get("end_time"),
            "patient_name": patient.get("name"),
            "patient_phone": patient.get("phone"),
        }
