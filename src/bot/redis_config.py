# inside src/bot/redis_config.py
import os
import json
import asyncio

try:
    import redis.asyncio as aioredis
    env_redis_url = os.getenv("REDIS_URL")
    if env_redis_url:
        REDIS_PROVIDER = env_redis_url
    else:
        REDIS_PROVIDER = "redis://127.0.0.1:6379"

    redis_client = aioredis.from_url(REDIS_PROVIDER, decode_responses=True)
    print(f"⚡ Redis engine successfully initialized via: {REDIS_PROVIDER}")
except Exception as redis_err:
    print(f"💥 Failed to initialize Redis cache engine: {redis_err}")
    redis_client = None

# تعریف صف لاگ‌ها به صورت مستقل
log_queue = asyncio.Queue()

# ابزارهای کش که از ردیس استفاده می‌کنند
async def cache_set_user_context(user_id: int, context_dict: dict, ttl: int = 1800):
    if redis_client:
        try:
            await redis_client.set(f"user_ctx:{user_id}", json.dumps(context_dict), ex=ttl)
        except Exception: pass

async def cache_invalidate_user(user_id: int):
    if redis_client:
        try:
            await redis_client.delete(f"user_ctx:{user_id}")
        except Exception: pass