"""
Burst rate limiter — protects Tiingo/Tavily/Groq spend and render load
regardless of credit balance. Fails OPEN if Redis is down: a limiter outage
shouldn't block legitimate research requests.

Fixed-window counters via INCR+EXPIRE, per-minute AND per-hour buckets,
keyed by user_id — same pattern as proposal-builder's rate_limiter.py.
"""

import logging
import math
import time
from typing import Tuple

from app.core.cache import get_redis
from app.core.config import settings

logger = logging.getLogger(__name__)


def _minute_key(user_id: str) -> str:
    bucket = math.floor(time.time() / 60)
    return f"ratelimit:market_research:min:{user_id}:{bucket}"


def _hour_key(user_id: str) -> str:
    bucket = math.floor(time.time() / 3600)
    return f"ratelimit:market_research:hr:{user_id}:{bucket}"


async def check_rate_limit(user_id: str) -> Tuple[bool, int]:
    """
    Returns (is_limited, retry_after_seconds).
    Fails open on Redis errors — returns (False, 0).
    """
    try:
        client = await get_redis()
        min_key = _minute_key(user_id)
        hr_key = _hour_key(user_id)

        pipe = client.pipeline()
        pipe.incr(min_key)
        pipe.expire(min_key, 120)
        pipe.incr(hr_key)
        pipe.expire(hr_key, 7200)
        results = await pipe.execute()

        minute_count = results[0]
        hour_count = results[2]

        if minute_count > settings.rate_limit_per_minute:
            return True, 60
        if hour_count > settings.rate_limit_per_hour:
            return True, 3600

        return False, 0

    except Exception as e:
        logger.warning(f"Rate limit check failed for user={user_id}, failing open: {e}")
        return False, 0
