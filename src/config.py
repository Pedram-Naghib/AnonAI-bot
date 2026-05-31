import os
from dotenv import load_dotenv

# لود کردن فایل .env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# بررسی وجود توکن‌ها برای جلوگیری از ارورهای مبهم بعدی
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("خطا: TELEGRAM_BOT_TOKEN در فایل .env تعریف نشده است!")
if not GEMINI_API_KEY:
    raise ValueError("خطا: GEMINI_API_KEY در فایل .env تعریف نشده است!")