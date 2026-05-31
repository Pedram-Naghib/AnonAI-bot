import asyncio
import uvicorn
from fastapi import FastAPI, Request
from telebot.types import Update
from telebot.async_telebot import AsyncTeleBot
from src.config import TELEGRAM_BOT_TOKEN
from src.bot.handlers import register_bot_handlers
from src.database.db_manager import init_db

# 🎛️ تنظیمات سوئیچ: True برای وب‌هوک (سرور واقعی) | False برای پولینگ (تست لوکال)
USE_WEBHOOK = False  

# 🌐 تنظیمات سرور وب‌هوک (زمانی که USE_WEBHOOK = True باشد)
WEBHOOK_HOST = "your_domain.com"  # آیدی دامنه یا آی‌پي سرور شما (بدون https)
WEBHOOK_PORT = 8000
WEBHOOK_URL = f"https://{WEBHOOK_HOST}/webhook/{TELEGRAM_BOT_TOKEN}"

# مقداردهی اولیه ربات
bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)
app = FastAPI()

# تعریف مسیر دریافت آپدیت‌ها برای وب‌هوک تلگرام
@app.post(f"/webhook/{TELEGRAM_BOT_TOKEN}")
async def telegram_webhook(request: Request):
    """دریافت آپدیت‌ها از تلگرام و تزریق به ربات"""
    json_string = await request.json()
    update = Update.de_json(json_string)
    await bot.process_new_updates([update])
    return {"status": "ok"}

async def start_bot():
    # ۱. اول دیتابیس را می‌سازیم
    print("🗄️ Initializing SQLite database...")
    await init_db()
    
    # ۲. ثبت هندلرها
    print("🔌 Registering bot handlers...")
    register_bot_handlers(bot)
    
    # ۳. انتخاب مسیر بر اساس متغیر سوئیچ
    if USE_WEBHOOK:
        # 🔔 سناریو اول: وب‌هوک (مناسب سرور واقعی)
        print("🔔 Setting up Webhook...")
        await bot.remove_webhook()
        # ست کردن آدرس وب‌هوک در سرور تلگرام
        await bot.set_webhook(url=WEBHOOK_URL, allowed_updates=["message", "callback_query", "message_reaction"])
        print(f"🚀 Webhook set on: {WEBHOOK_URL}")
        
        # اجرای سرور وب با uvicorn در پس‌زمینه
        config = uvicorn.Config(app=app, host="0.0.0.0", port=WEBHOOK_PORT, loop="asyncio")
        server = uvicorn.Server(config)
        await server.serve()
    else:
        # 🔄 سناریو دوم: پولینگ (مناسب تست روی لپ‌تاپ خودت)
        print("🔄 Removing any active webhooks and starting Long Polling...")
        await bot.remove_webhook() # پاک کردن وب‌هوک‌های قبلی تا پولینگ ارور ندهد
        print("🤖 ServantBot is online via Polling...")
        await bot.infinity_polling(
            logger_level=20, 
            allowed_updates=["message", "callback_query", "message_reaction"]
        )

if __name__ == "__main__":
    asyncio.run(start_bot())