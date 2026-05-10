"""
Redis client for embedding cache.

Provides graceful degradation — if REDIS_URL is not set or Redis is
unreachable, every function is a no-op and the app works as before.

Cache strategy:
  - Key:   embed:{model}:{md5(text)}
  - Value: JSON-serialised list[float]
  - TTL:   24 h (86 400 s)  — embeddings for the same text never change
"""

import hashlib
import json
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

_redis = None          # redis.asyncio.Redis  |  None when disabled


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def init_redis(url: str) -> None:
    """Call once at app startup.  url="" → caching silently disabled."""
    global _redis
    if not url:
        logger.info("[Redis] REDIS_URL not configured — embedding cache disabled")
        return
    try:
        import redis.asyncio as aioredis          # imported lazily so the app
        _redis = aioredis.from_url(               # starts even without redis pkg
            url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=2,
        )
        await _redis.ping()
        logger.info("[Redis] Connected and ready")
    except Exception as exc:
        logger.warning(f"[Redis] Could not connect ({exc}) — caching disabled")
        _redis = None


async def close_redis() -> None:
    """Call once at app shutdown."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("[Redis] Connection closed")


# ---------------------------------------------------------------------------
# Embedding cache helpers
# ---------------------------------------------------------------------------

def _embed_key(model: str, text: str) -> str:
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"embed:{model}:{digest}"


async def get_cached_embedding(model: str, text: str) -> Optional[List[float]]:
    """Return cached vector or None on miss / error / disabled."""
    if _redis is None:
        return None
    try:
        raw = await _redis.get(_embed_key(model, text))
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning(f"[Redis] get_cached_embedding error: {exc}")
    return None


async def set_cached_embedding(
    model: str,
    text: str,
    vector: List[float],
    ttl: int = 86_400,          # 24 h
) -> None:
    """Store vector in Redis with TTL.  Silent no-op on any error."""
    if _redis is None:
        return
    try:
        await _redis.setex(_embed_key(model, text), ttl, json.dumps(vector))
    except Exception as exc:
        logger.warning(f"[Redis] set_cached_embedding error: {exc}")
