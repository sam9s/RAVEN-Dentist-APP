"""Slack webhook router stub."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.services.cache import cache_get, cache_set
from backend.utils.config import get_settings

router = APIRouter()


class SlackMessage(BaseModel):
    """Incoming Slack message payload."""

    user_id: str
    text: str


@router.post("/events")
def handle_slack_event(message: SlackMessage, settings=Depends(get_settings)) -> dict[str, str]:
    """Stub handler for Slack events endpoint."""

    cache_key = f"slack:last_message:{message.user_id}"
    cache_set(cache_key, message.text, ex=300)

    stored_message = cache_get(cache_key)
    if stored_message is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cache message")

    return {
        "status": "received",
        "echo": stored_message,
        "slack_bot_token_present": str(bool(settings.slack_bot_token)),
    }
