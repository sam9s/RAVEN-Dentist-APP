"""Redis cache client utilities."""

from typing import Any, Optional

import redis

from backend.utils.config import get_settings

settings = get_settings()

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def cache_set(key: str, value: Any, ex: Optional[int] = None) -> bool:
    """Set a value in Redis with optional expiration."""

    return bool(redis_client.set(name=key, value=value, ex=ex))


def cache_get(key: str) -> Optional[str]:
    """Get a value from Redis by key."""

    return redis_client.get(name=key)
