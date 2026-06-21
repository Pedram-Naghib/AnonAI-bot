import os
import asyncio
import signal
import secrets

import uvicorn
from fastapi import FastAPI, Request, Response
from telebot.types import Update
from telebot.async_telebot import AsyncTeleBot

from src.config import TELEGRAM_BOT_TOKEN, EMOJI, SUPER_USERS, WEBHOOK_HOST
from src.bot.handlers import register_bot_handlers
from src.database.db_manager import init_db
from src.bot.redis_config import ping_redis
from src.bot.background_workers import (
    background_log_worker,
    background_matchmaking_worker,
    background_broadcast_worker,
    background_cleanup_worker,
)

# ── Deployment config ─────────────────────────────────────
# Set USE_WEBHOOK=false in .env to run locally with polling
USE_WEBHOOK  = "true"
WEBHOOK_PORT = int(os.getenv("PORT", "8000"))
WEBHOOK_URL  = f"https://{WEBHOOK_HOST}/webhook/{TELEGRAM_BOT_TOKEN}"

# Shared secret so only Telegram can call our webhook. If you don't set one in the
# environment, a fresh random secret is generated on each startup (the webhook is
# re-registered at startup anyway, so Telegram always has the matching value).
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip() or secrets.token_urlsafe(32)

ALLOWED_UPDATES = ["message", "callback_query", "message_reaction", "inline_query", "chosen_inline_result"]

bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)
app = FastAPI()


# ── Health check ──────────────────────────────────────────
@app.api_route("/", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "alive"}


# ── Webhook endpoint ──────────────────────────────────────
@app.post(f"/webhook/{TELEGRAM_BOT_TOKEN}")
async def telegram_webhook(request: Request):
    # Telegram echoes back the secret we registered. Reject anything that doesn't
    # carry it — that's how we know the request is really from Telegram.
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        return Response(status_code=403)

    json_data = await request.json()
    update    = Update.de_json(json_data)
    await bot.process_new_updates([update])
    return {"status": "ok"}


# ── Startup notification ──────────────────────────────────
async def send_startup_notification():
    try:
        await asyncio.sleep(3)  # Wait for webhook to register on Telegram's side
        bot_info = await bot.get_me()
        msg = (
            f"{EMOJI['thunder']['html']} <b>پلتفرم با موفقیت آپدیت و بالا آمد!</b>\n"
            "───────────────────\n"
            f"{EMOJI['bot']['html']} <b>ربات:</b> @{bot_info.username}\n"
            f"{EMOJI['green_dot']['html']} <b>وضعیت:</b> فعال و آماده\n"
            f"{EMOJI['lock']['html']} <i>لوکال مموری پاکسازی و مجدداً لود شد.</i>"
        )
        # Notify all super users, not just one hardcoded ID
        for admin_id in SUPER_USERS:
            try:
                await bot.send_message(admin_id, msg, parse_mode="HTML")
            except Exception:
                pass
        print("✅ Startup notification sent.")
    except Exception as e:
        print(f"💥 Startup notification error: {e}")


# ── Main startup sequence ─────────────────────────────────
async def start_bot():
    print("🗄️  Initializing database...")
    await init_db()

    print("⚡ Checking Redis connectivity...")
    await ping_redis()

    print("🔌 Registering handlers...")
    register_bot_handlers(bot)

    print("⚙️  Starting background workers...")
    asyncio.create_task(background_log_worker(bot))
    asyncio.create_task(background_matchmaking_worker(bot))
    asyncio.create_task(background_broadcast_worker(bot))
    asyncio.create_task(background_cleanup_worker(bot))

    asyncio.create_task(send_startup_notification())

    if USE_WEBHOOK:
        print(f"🔔 Setting webhook → {WEBHOOK_URL}")
        await bot.remove_webhook()
        await bot.set_webhook(url=WEBHOOK_URL, allowed_updates=ALLOWED_UPDATES, secret_token=WEBHOOK_SECRET)

        config = uvicorn.Config(app=app, host="0.0.0.0", port=WEBHOOK_PORT, loop="asyncio")
        server = uvicorn.Server(config)

        # Graceful shutdown on SIGTERM (Render sends this before killing the container)
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(server.shutdown()))

        await server.serve()
    else:
        print("🔄 Starting long polling (local mode)...")
        await bot.remove_webhook()
        await bot.infinity_polling(logger_level=20, allowed_updates=ALLOWED_UPDATES)


if __name__ == "__main__":
    asyncio.run(start_bot())