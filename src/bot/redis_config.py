# inside src/bot/redis_config.py
import os
import json
import asyncio
from telebot.async_telebot import AsyncTeleBot  # 🔥 حل باگ عدم ایمپورت Type Hint ربات

# ثابت‌های عمومی که کل سیستم به آن‌ها نیاز دارند
LOG_GROUP_ID = -5295499371

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

# ⚡ تعریف صف لاگ‌ها به صورت مستقل و اتمیک (فقط یک‌بار)
log_queue = asyncio.Queue()


# ==========================================
# ⚡ سیستم لاگر دسته‌ای (Log Batching Worker) - جلوگیری از لیمیت تلگرام
# ==========================================
async def send_bot_log(bot: AsyncTeleBot, message, action_name: str, extra_details: str = ""):
    try:
        user = message.from_user
        if user.id == 8627765327: return
        log_text = (
            f"📥 <b>[LOG] فعالیت جدید در ربات</b>\n"
            f"👤 <b>کاربر:</b> {user.first_name}\n"
            f"🪪 <b>آیدی عددی:</b> <code>{message.chat.id}</code>\n"
            f"🆔 <b>یوزرنیم:</b> @{user.username or 'No_Username'}\n"
            f"🛠 <b>اکشن:</b> <code>{action_name}</code>\n"
        )
        if extra_details: log_text += f"📝 <b>جزئیات:</b> {extra_details}\n"
        await log_queue.put(log_text)
    except Exception as e:
        print(f"💥 Failed to queue log: {e}")


# ==========================================
# ⚡ ابزار کمکی کش: متدهای هم‌زمان اتمیک مدیریت حافظه موقت (Cache Helpers)
# ==========================================
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