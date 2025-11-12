"""Application configuration utilities."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    app_name: str = Field(default="Dentist Appointment Scheduler")
    app_version: str = Field(default="0.1.0")

    postgres_url: str = Field(default="postgresql+psycopg://user:pass@localhost:5432/dentist")
    redis_url: str = Field(default="redis://localhost:6379/0")
    google_api_key: str = Field(default="change-me")
    slack_bot_token: str = Field(default="xoxb-change-me")
    email_smtp: str = Field(default="smtp://user:pass@smtp.example.com:587")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
