"""cal.com Calendar API adapter."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx

LOGGER = logging.getLogger(__name__)


class CalComAdapter:
    """Adapter for interacting with the cal.com scheduling API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.cal.com/v1",
        event_type_id: Optional[int] = None,
        calendar_id: Optional[str] = None,
        timezone: str = "Asia/Kolkata",
        event_duration_minutes: int = 30,
        use_stub: bool = False,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.event_type_id = event_type_id
        self.calendar_id = calendar_id
        self.timezone = timezone
        self.event_duration_minutes = max(1, event_duration_minutes)
        self.use_stub = use_stub or not api_key or not event_type_id
        self._timeout = timeout_seconds
        self._availability_url = "https://api.cal.com/v2/slots"

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def check_availability(self, preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return availability slots from cal.com.

        Falls back to deterministic test data if the adapter is in stub mode or
        if the API call fails.
        """

        LOGGER.info(
            "cal.com availability: use_stub=%s event_type_id=%s",
            self.use_stub,
            self.event_type_id,
        )

        if self.use_stub:
            return self._stub_slots(preferences)

        try:
            params = self._build_availability_params(preferences)
            with self._http_client() as client:
                response = client.get(self._availability_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("cal.com availability failed: %s", exc)
            return self._stub_slots(preferences)

        slots = self._coerce_slots(payload) or []
        if not slots:
            return []

        dentist_id = preferences.get("dentist_id")
        normalized: List[Dict[str, Any]] = []
        for item in slots:
            start_time = (
                item.get("startTime")
                or item.get("start_time")
                or item.get("start")
            )
            end_time = (
                item.get("endTime")
                or item.get("end_time")
                or self._calculate_end_time(start_time)
            )
            slot_id = item.get("uid") or item.get("id") or item.get("slot_id")
            if not (start_time and end_time):
                continue
            normalized.append(
                {
                    "slot_id": slot_id or f"{start_time}",
                    "start_time": start_time,
                    "end_time": end_time,
                    "dentist_id": dentist_id,
                }
            )

        return normalized

    def book_appointment(
        self,
        *,
        slot: Dict[str, Any],
        patient: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Book an appointment via cal.com.

        Returns a normalized booking dict containing key identifiers.
        """

        LOGGER.info(
            "cal.com booking: use_stub=%s slot_id=%s",
            self.use_stub,
            slot.get("slot_id") or slot.get("start_time"),
        )

        if self.use_stub:
            return self._stub_booking(slot=slot, patient=patient)

        payload = self._build_booking_payload(slot=slot, patient=patient)

        try:
            with self._http_client() as client:
                LOGGER.debug(
                    "cal.com booking request: %s",
                    json.dumps(payload, default=str),
                )
                response = client.post(
                    "/bookings",
                    params={"apiKey": self.api_key},
                    json=payload,
                )
                response.raise_for_status()
                LOGGER.debug(
                    "cal.com booking response: %s %s",
                    response.status_code,
                    response.text,
                )
                booking_payload = response.json()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - defensive
            detail = exc.response.text if exc.response else ""
            LOGGER.error(
                "cal.com booking failed: status=%s body=%s",
                getattr(exc.response, "status_code", "unknown"),
                detail,
            )
            return None
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("cal.com booking failed: %s", exc)
            return None

        booking = self._coerce_booking(booking_payload)
        if not booking:
            return None

        return booking

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _http_client(self) -> httpx.Client:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "cal-api-version": "2024-09-04",
        }
        return httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self._timeout,
        )

    def _build_availability_params(self, preferences: Dict[str, Any]) -> Dict[str, Any]:
        date_str = preferences.get("date")
        tz = ZoneInfo(self.timezone)

        if date_str:
            try:
                target_date = datetime.fromisoformat(date_str)
                if target_date.tzinfo is None:
                    target_date = target_date.replace(tzinfo=tz)
            except ValueError:
                target_date = datetime.now(tz)
        else:
            target_date = datetime.now(tz)

        start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        start_utc = start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "eventTypeId": self.event_type_id,
            "start": start_utc,
            "end": end_utc,
            "timeZone": self.timezone,
        }

    @staticmethod
    def _coerce_slots(payload: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        if not payload:
            return None

        data = payload.get("data")
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            slots: List[Dict[str, Any]] = []
            for value in data.values():
                if isinstance(value, list):
                    slots.extend(value)
            if slots:
                return slots

        return payload.get("slots") or payload.get("availableSlots")

    def _calculate_end_time(self, start_time: Optional[str]) -> Optional[str]:
        if not start_time:
            return None

        try:
            normalized = start_time.replace("Z", "+00:00")
            start_dt = datetime.fromisoformat(normalized)
        except ValueError:
            LOGGER.debug("Unable to parse slot start time: %s", start_time)
            return None

        end_dt = start_dt + timedelta(minutes=self.event_duration_minutes)
        return end_dt.isoformat()

    def _build_booking_payload(
        self,
        *,
        slot: Dict[str, Any],
        patient: Dict[str, Any],
    ) -> Dict[str, Any]:
        attendee = {
            "name": patient.get("name") or patient.get("full_name", "Patient"),
            "email": patient.get("email"),
            "timeZone": self.timezone,
            "language": "en",
        }

        metadata = {
            "phone": patient.get("phone"),
            "reason": patient.get("reason"),
        }

        responses: Dict[str, Any] = {}
        patient_name = attendee["name"]
        patient_email = attendee["email"]
        patient_phone = patient.get("phone")

        if patient_name:
            responses["name"] = patient_name
        if patient_email:
            responses["email"] = patient_email
        if patient_phone:
            responses["phoneNumber"] = patient_phone

        payload: Dict[str, Any] = {
            "eventTypeId": self.event_type_id,
            "start": slot.get("start_time"),
            "end": slot.get("end_time"),
            "startTime": slot.get("start_time"),  # backwards compatibility
            "endTime": slot.get("end_time"),
            "attendees": [attendee],
            "metadata": {k: v for k, v in metadata.items() if v} or {},
            "timeZone": self.timezone,
            "language": "en",
            "responses": responses,
        }

        if self.calendar_id:
            payload["booking"] = {"destinationCalendarId": self.calendar_id}

        return payload

    @staticmethod
    def _coerce_booking(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        data = payload.get("data") if isinstance(payload, dict) else None
        booking = data or payload

        status = str(booking.get("status", "PENDING")).upper()

        return {
            "calcom_booking_id": booking.get("id")
            or booking.get("uid")
            or booking.get("bookingId"),
            "status": status,
            "start_time": booking.get("startTime"),
            "end_time": booking.get("endTime"),
            "attendee_email": (
                booking.get("attendees", [{}])[0].get("email")
                if booking.get("attendees")
                else None
            ),
        }

    def _stub_slots(self, preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
        preferred_date = preferences.get("date") or datetime.now().date().isoformat()
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

    def _stub_booking(
        self,
        *,
        slot: Dict[str, Any],
        patient: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "calcom_booking_id": f"booking-{slot.get('slot_id', slot.get('start_time'))}",
            "status": "PENDING",
            "start_time": slot.get("start_time"),
            "end_time": slot.get("end_time"),
            "patient_name": patient.get("name"),
            "patient_phone": patient.get("phone"),
        }
