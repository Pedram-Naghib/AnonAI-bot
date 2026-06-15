import os
import asyncio
import uvicorn
from fastapi import FastAPI, Request
from telebot.types import Update
from telebot.async_telebot import AsyncTeleBot
from src.config import TELEGRAM_BOT_TOKEN, EMOJI
from src.bot.handlers import register_bot_handlers
from src.database.db_manager import init_db

# 🔥 ایمپورت کردن ورکرهای پس‌زمینه جدید برای لود هم‌زمان در لوپ اصلی
from src.bot.background_workers import background_log_worker, background_matchmaking_worker, background_broadcast_worker

# 🎛 تنظیمات ران شدن (روی سیستم خودت False بگذار، روی سرور رندر True)
USE_WEBHOOK = True

WEBHOOK_HOST = "anonai-bot.onrender.com"
WEBHOOK_PORT = int(os.environ.get("PORT", 8000))
WEBHOOK_URL = f"https://{WEBHOOK_HOST}/webhook/{TELEGRAM_BOT_TOKEN}"

# لیست آپدیت‌های مجاز برای لاگ‌گیری چت‌ها و ری‌آکشن‌ها
ALLOWED_UPDATES = ["message", "callback_query", "message_reaction", "inline_query", "chosen_inline_result"]

bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)
app = FastAPI()

# ==========================================
# 🚀 تابع اختصاصی ارسال نوتیفیکیشن لایو شدن ربات
# ==========================================
async def send_startup_notification(bot_instance):
    try:
        # چند ثانیه صبر می‌کنیم تا وب‌هوک کاملاً روی سرورهای تلگرام مستقر و تایید شود
        await asyncio.sleep(3)
        bot_info = await bot_instance.get_me()
        
        # 💎 اعمال لایه ['html'] دیکشنری جدید برای رندر انیمیشن‌های لایو پکت در بدنه پیام
        startup_msg = (
            f"{EMOJI['thunder']['html']} <b>پلتفرم با موفقیت آپدیت شد و بالا آمد!</b>\n"
            "───────────────────\n"
            f"{EMOJI['bot']['html']} <b>ربات:</b> @{bot_info.username}\n"
            f"{EMOJI['green_dot']['html']} <b>وضعیت:</b> فعال و آمادهٔ شلیک نجوا\n"
            f"{EMOJI['lock']['html']} <i>لوکال مموری با موفقیت پاکسازی و مجدداً لود شد.</i>"
        )
        await bot_instance.send_message(8627765327, startup_msg, parse_mode="HTML")
        print("✅ پیام استارت‌آپ با موفقیت برای ادمین ارسال شد.")
    except Exception as e:
        print(f"💥 خطای ارسال پیام استارت‌آپ: {e}")

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
    
    # 🔥 ۳. روشن کردن ورکرهای اتمیک پس‌زمینه درون Event Loop جاری
    print("⚡ Activating Background Workers (Log Queue & Matchmaking)...")
    asyncio.create_task(background_log_worker(bot))
    asyncio.create_task(background_matchmaking_worker(bot))
    
    # 🔥 فعال‌سازی ورکر همگانی دسته‌ای
    asyncio.create_task(background_broadcast_worker(bot))
    
    # 🔥 ۴. فعال‌سازی موتور اعلان لایو شدن ربات در پس‌زمینه بدون مسدود کردن سرور
    asyncio.create_task(send_startup_notification(bot))
    
    # ۵. انتخاب مسیر ران کردن (وب‌هوک یا پولینگ)
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
        print("🤖 CyberAnons is online via Polling...")
        # اجرای بدون وقفه پولینگ لوکال
        await bot.infinity_polling(logger_level=20, allowed_updates=ALLOWED_UPDATES)

if __name__ == "__main__":
    # اجرای استاندارد ناهمگام کل ساختار سرور
    asyncio.run(start_bot())