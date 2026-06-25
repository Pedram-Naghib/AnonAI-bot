import os
import json
import html
import asyncio

from telebot.async_telebot import AsyncTeleBot
from src.config import LOG_GROUP_ID, SUPER_USERS

# ── Redis init ────────────────────────────────────────────
try:
    import redis.asyncio as aioredis

    _redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
    
    # 🌟 اضافه شدن health_check_interval برای زنده نگه داشتن کانکشن در سرور
    redis_client = aioredis.from_url(
        _redis_url, 
        decode_responses=True, 
        health_check_interval=30
    )

    # Log provider type only, never the full URL (may contain password)
    _provider = "local" if "127.0.0.1" in _redis_url or "localhost" in _redis_url else "remote"
    print(f"⚡ Redis engine initialized ({_provider})")

except Exception as e:
    print(f"💥 Failed to initialize Redis: {e}")
    redis_client = None

# ── In-memory log queue (persists only while process is alive) ──
log_queue: asyncio.Queue = asyncio.Queue()


# ── Log helper ────────────────────────────────────────────
async def send_bot_log(bot: AsyncTeleBot, message, action_name: str, extra_details: str = ""):
    """Queue a log entry for the batch log worker. Skips messages from super users."""
    try:
        user = message.from_user
        # Don't log actions taken by admins/super users
        if user.id in SUPER_USERS:
            return

        log_text = (
            f"📥 <b>[LOG] فعالیت جدید در ربات</b>\n"
            f"👤 <b>کاربر:</b> {html.escape(user.first_name or '')}\n"
            f"🪪 <b>آیدی عددی:</b> <code>{message.chat.id}</code>\n"
            f"🆔 <b>یوزرنیم:</b> @{user.username or 'No_Username'}\n"
            f"🛠 <b>اکشن:</b> <code>{action_name}</code>\n"
        )
        if extra_details:
            log_text += f"📝 <b>جزئیات:</b> {extra_details}\n"

        await log_queue.put(log_text)
    except Exception as e:
        print(f"💥 Failed to queue log: {e}")


# ── Cache helpers ─────────────────────────────────────────
async def cache_set_user_context(user_id: int, context_dict: dict, ttl: int = 1800):
    if not redis_client:
        return
    try:
        await redis_client.set(f"user_ctx:{user_id}", json.dumps(context_dict), ex=ttl)
    except Exception:
        pass


async def cache_invalidate_user(user_id: int):
    if not redis_client:
        return
    try:
        await redis_client.delete(f"user_ctx:{user_id}")
    except Exception:
        pass


# ── Startup connectivity check ────────────────────────────
async def ping_redis() -> bool:
    """Call once on startup to verify Redis is reachable."""
    if not redis_client:
        return False
    try:
        await redis_client.ping()
        print("✅ Redis connection verified.")
        return True
    except Exception as e:
        print(f"⚠️ Redis ping failed — caching disabled: {e}")
        return False