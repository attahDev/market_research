import json
import logging
from typing import Any, Optional
import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None

def lock_key(query_normalized: str) -> str:
    return f"research:lock:{query_normalized}"

def status_key(job_id: str) -> str:
    return f"research:status:{job_id}"

def result_key(query_normalized: str) -> str:
    return f"research:result:{query_normalized}"

async def cache_get(key: str) -> Optional[Any]:
    try:
        client = await get_redis()
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Cache GET failed for key={key}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int) -> bool:
    try:
        client = await get_redis()
        await client.setex(key, ttl, json.dumps(value))
        return True
    except Exception as e:
        logger.warning(f"Cache SET failed for key={key}: {e}")
        return False


async def cache_delete(key: str) -> bool:
    try:
        client = await get_redis()
        await client.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Cache DELETE failed for key={key}: {e}")
        return False

async def acquire_lock(query_normalized: str, job_id: str) -> bool:
    try:
        client = await get_redis()
        key = lock_key(query_normalized)
        result = await client.set(
            key,
            job_id,
            nx=True,
            ex=settings.job_inflight_lock_seconds,
        )
        return result is True
    except Exception as e:
        logger.warning(f"Lock acquire failed for query={query_normalized}: {e}")
        return False


async def get_inflight_job_id(query_normalized: str) -> Optional[str]:
    try:
        client = await get_redis()
        key = lock_key(query_normalized)
        return await client.get(key)
    except Exception as e:
        logger.warning(f"Lock get failed for query={query_normalized}: {e}")
        return None


async def release_lock(query_normalized: str) -> bool:
    return await cache_delete(lock_key(query_normalized))


async def set_job_status(job_id: str, status: str) -> None:
    try:
        client = await get_redis()
        await client.setex(status_key(job_id), 7200, status)
    except Exception as e:
        logger.warning(f"Status set failed for job={job_id}: {e}")


async def get_job_status(job_id: str) -> Optional[str]:
    try:
        client = await get_redis()
        return await client.get(status_key(job_id))
    except Exception as e:
        logger.warning(f"Status get failed for job={job_id}: {e}")
        return None

async def cache_result(query_normalized: str, result: dict, category: str) -> None:
    ttl = settings.get_cache_ttl(category)
    await cache_set(result_key(query_normalized), result, ttl)


async def get_cached_result(query_normalized: str) -> Optional[dict]:
    return await cache_get(result_key(query_normalized))
