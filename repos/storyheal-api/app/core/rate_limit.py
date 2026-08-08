"""Small Redis-backed fixed-window limiter for unauthenticated integration endpoints."""

import time
from collections import defaultdict

from fastapi import HTTPException, Request

from app.core.config import settings

_fallback: dict[tuple[str, int], int] = defaultdict(int)
_redis = None


async def public_rate_limit(request: Request) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    identity = request.client.host if request.client else "unknown"
    route = request.url.path
    window = int(time.time() // 60)
    redis_key = f"storyheal:rate:{route}:{identity}:{window}"
    count: int
    global _redis
    if settings.REDIS_URL:
        try:
            if _redis is None:
                import redis.asyncio as redis
                _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            count = int(await _redis.incr(redis_key))
            if count == 1:
                await _redis.expire(redis_key, 70)
        except Exception:
            key = (f"{route}:{identity}", window)
            _fallback[key] += 1
            count = _fallback[key]
    else:
        key = (f"{route}:{identity}", window)
        _fallback[key] += 1
        count = _fallback[key]
    if len(_fallback) > 10_000:
        for old_key in [key for key in _fallback if key[1] < window - 1]:
            _fallback.pop(old_key, None)
    if count > settings.RATE_LIMIT_REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "60"})
