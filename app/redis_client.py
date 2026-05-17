import redis.asyncio as aioredis
import time
import os
from typing import Dict

redis_client = None
redis_available = False
in_memory_blacklist: Dict[str, float] = {}

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


async def init_redis() -> None:
    global redis_client, redis_available
    try:
        redis_client = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )
        await redis_client.ping()
        redis_available = True
        print("Redis connected successfully")
    except Exception as e:
        print(f"Redis connection failed: {e}. Using in-memory fallback.")
        redis_available = False
        redis_client = None


async def close_redis() -> None:
    global redis_client
    if redis_client:
        try:
            await redis_client.aclose()
        except Exception as e:
            print(f"Error closing Redis: {e}")


async def blacklist_token(token: str, expires_in_seconds: int) -> None:
    if redis_available and redis_client:
        try:
            await redis_client.setex(f"blacklist:{token}", expires_in_seconds, "true")
            return
        except Exception as e:
            print(f"Redis setex failed: {e}")
    # Fallback to in-memory
    in_memory_blacklist[token] = time.time() + expires_in_seconds


async def is_token_blacklisted(token: str) -> bool:
    if redis_available and redis_client:
        try:
            result = await redis_client.exists(f"blacklist:{token}")
            return bool(result)
        except Exception as e:
            print(f"Redis check failed: {e}")

    # Fallback to in-memory
    expiry = in_memory_blacklist.get(token)
    if expiry is None:
        return False
    if time.time() < expiry:
        return True
    del in_memory_blacklist[token]
    return False
