"""Patient ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.appointment import Appointment
else:  # pragma: no cover - typing runtime fallback
    Appointment = "Appointment"  # type: ignore[assignment]


class Patient(Base):
    """Represents a patient interacting with the clinic."""

    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    appointments: Mapped[List["Appointment"]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
    )
