"""Application configuration utilities."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    app_name: str = Field(
        default="Dentist Appointment Scheduler",
    )
    app_version: str = Field(
        default="0.1.0",
    )

    postgres_url: str = Field(
        default="postgresql+psycopg://user:pass@localhost:5432/dentist",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
    )
    cal_api_key: str = Field(
        default="change-me",
    )
    slack_bot_token: str = Field(
        default="xoxb-change-me",
    )
    slack_app_token: str = Field(
        default="xapp-change-me",
    )
    slack_signing_secret: str = Field(
        default="change-me",
    )
    email_smtp: str = Field(
        default="smtp://user:pass@smtp.example.com:587",
    )
    openai_api_key: str = Field(
        default="change-me",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
    )
    n8n_webhook_url: str = Field(
        default="https://n8n.example.com/webhook/appointment.booked",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
