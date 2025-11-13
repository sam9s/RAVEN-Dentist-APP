"""Appointment model definition."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.dentist import Dentist
    from backend.models.patient import Patient
else:  # pragma: no cover - typing runtime fallback
    Dentist = "Dentist"  # type: ignore[assignment]
    Patient = "Patient"  # type: ignore[assignment]


class Appointment(Base):
    """Represents a dentist appointment booking."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
    )
    dentist_id: Mapped[int] = mapped_column(
        ForeignKey("dentists.id"),
        nullable=False,
    )
    calcom_booking_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    patient: Mapped["Patient"] = relationship(back_populates="appointments")
    dentist: Mapped["Dentist"] = relationship(back_populates="appointments")
