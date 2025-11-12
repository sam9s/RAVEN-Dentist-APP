"""Appointment model definition."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class Appointment(Base):
    """Represents a dentist appointment booking."""

    __tablename__ = "appointments"

    id: int = Column(Integer, primary_key=True, index=True)
    patient_name: str = Column(String(255), nullable=False)
    patient_email: str = Column(String(255), nullable=False)
    preferred_time: datetime = Column(DateTime, nullable=False)
    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)


