import os
import asyncio
import uvicorn
from fastapi import FastAPI, Request
from telebot.types import Update
from telebot.async_telebot import AsyncTeleBot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import TELEGRAM_BOT_TOKEN
from src.bot.handlers import register_bot_handlers
from src.bot.tasks import send_daily_analytics
from src.database.db_manager import init_db

# 🎛 تنظیمات ران شدن (روی سیستم خودت False بگذار، روی سرور رندر True)
USE_WEBHOOK = True

WEBHOOK_HOST = "anonai-bot.onrender.com"
WEBHOOK_PORT = int(os.environ.get("PORT", 8000))
WEBHOOK_URL = f"https://{WEBHOOK_HOST}/webhook/{TELEGRAM_BOT_TOKEN}"

# لیست آپدیت‌های مجاز برای لاگ‌گیری چت‌ها و ری‌آکشن‌ها
ALLOWED_UPDATES = ["message", "callback_query", "message_reaction"]

bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)
app = FastAPI()

@app.api_route("/", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "alive"}

@app.post(f"/webhook/{TELEGRAM_BOT_TOKEN}")
async def telegram_webhook(request: Request):
    json_string = await request.json()
    update = Update.de_json(json_string)
    await bot.process_new_updates([update])
    return {"status": "ok"}

async def start_bot():
    # ۱. مقداردهی اولیه دیتابیس ابری سوپابیس
    print("🗄️ Initializing Databases...")
    await init_db()
    
    # 🔌 ۲. ثبت هندلرهای اصلی ربات
    print("🔌 Registering bot handlers...")
    register_bot_handlers(bot)
    
    # ⏰ ۳. تنظیم اسکجولر گزارش ۲۴ ساعته با تزریق اِونت لوپ جاری
    # این کار مانع از کرش کردن متد ارسال پیام ربات در بک‌آند می‌شود
    current_loop = asyncio.get_running_loop()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_analytics, 'cron', hour=23, minute=30, args=[bot])
    scheduler.start()
    print("Base Analytics scheduler started...")
    
    # ۴. انتخاب مسیر ران کردن (وب‌هوک یا پولینگ)
    if USE_WEBHOOK:
        print("🔔 Setting up Webhook...")
        await bot.remove_webhook()
        # ست کردن وب‌هوک همراه با فیلتر آپدیت‌ها
        await bot.set_webhook(url=WEBHOOK_URL, allowed_updates=ALLOWED_UPDATES)
        
        config = uvicorn.Config(app=app, host="0.0.0.0", port=WEBHOOK_PORT, loop="asyncio")
        server = uvicorn.Server(config)
        await server.serve()
    else:
        print("🔄 Starting Long Polling...")
        await bot.remove_webhook()
        print("🤖 Humban is online via Polling...")
        # اجرای بدون وقفه پولینگ لوکال
        await bot.infinity_polling(logger_level=20, allowed_updates=ALLOWED_UPDATES)

if __name__ == "__main__":
    # اجرای استاندارد ناهمگام
    asyncio.run(start_bot())