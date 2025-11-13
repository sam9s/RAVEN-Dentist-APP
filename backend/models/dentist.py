"""Dentist ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.appointment import Appointment


class Dentist(Base):
    """Represents a dentist or clinic calendar owner."""

    __tablename__ = "dentists"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    clinic_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    calcom_calendar_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    appointments: Mapped[List["Appointment"]] = relationship(
        back_populates="dentist",
        cascade="all, delete-orphan",
    )
