# app/redis_client.py
import redis.asyncio as aioredis
import time
from typing import Dict

redis_client = None
redis_available = False
in_memory_blacklist: Dict[str, float] = {}

async def init_redis():
    global redis_client, redis_available
    try:
        redis_client = aioredis.from_url(
            "redis://localhost:6379/0", 
            encoding="utf-8", 
            decode_responses=True,
            socket_connect_timeout=5,
            retry_on_timeout=True
        )
        await redis_client.ping()
        redis_available = True
        print("✓ Redis connected successfully")
    except Exception as e:
        print(f"⚠ Redis connection failed: {e}")
        print("  Using in-memory cache as fallback")
        redis_available = False
        redis_client = None

async def close_redis():
    global redis_client
    if redis_client:
        try:
            await redis_client.close()
        except Exception as e:
            print(f"Error closing Redis: {e}")

# Blacklist functions
async def blacklist_token(token: str, expires_in_seconds: int):
    if redis_available and redis_client:
        try:
            await redis_client.setex(f"blacklist:{token}", expires_in_seconds, "true")
        except Exception as e:
            print(f"Redis setex failed: {e}")
            in_memory_blacklist[token] = time.time() + expires_in_seconds
    else:
        in_memory_blacklist[token] = time.time() + expires_in_seconds

async def is_token_blacklisted(token: str) -> bool:
    current_time = time.time()
    
    if redis_available and redis_client:
        try:
            return await redis_client.exists(f"blacklist:{token}")
        except Exception as e:
            print(f"Redis exists check failed: {e}")
    
    if token in in_memory_blacklist:
        expiry_time = in_memory_blacklist[token]
        if current_time < expiry_time:
            return True
        else:
            del in_memory_blacklist[token]
    
    return False