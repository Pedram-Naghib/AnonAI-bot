import os
from dotenv import load_dotenv

# لود کردن فایل .env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROUP_CHAT_ID = -1001434396268
# بررسی وجود توکن‌ها برای جلوگیری از ارورهای مبهم بعدی
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("خطا: TELEGRAM_BOT_TOKEN در فایل .env تعریف نشده است!")
if not GEMINI_API_KEY:
    raise ValueError("خطا: GEMINI_API_KEY در فایل .env تعریف نشده است!")

# 💎 مرجع متغیرهای اموجی پرمیوم و متحرک پلتفرم CyberAnons

# اموجی‌های بخش نجوا و پیام‌های محرمانه
WHISPER_WAIT = "<tg-emoji emoji-id='5879791055489998105'>📬</tg-emoji>"
WHISPER_OPENED = "<tg-emoji emoji-id='5879798279624990117'>📭</tg-emoji>"
TARGET_LOCK = "<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji>"
SUCCESS_CHECK = "<tg-emoji emoji-id='5882153540905868842'>✅</tg-emoji>"
TRASH_CAN = "<tg-emoji emoji-id='5879496330539179820'>🗑</tg-emoji>"
SECRET_LOCK = "<tg-emoji emoji-id='5431239810239101111'>🔒</tg-emoji>"
BLOCK = "<tg-emoji emoji-id='5852969637561507022'>🚫</tg-emoji>"

# اموجی‌های بخش منو و راهنما
LIGHT_BULB = "<tg-emoji emoji-id='5879796677602187415'>💡</tg-emoji>"
# INFO_CYBER = "<tg-emoji emoji-id='5431239810239103333'>🔮</tg-emoji>"
FINGERPRINT_ID = "<tg-emoji emoji-id='5879852112745077416'>🆔</tg-emoji>"
ANON_MAIL = "<tg-emoji emoji-id='5443127283898405358'>📥</tg-emoji>"
# LOVE_LETTER = "<tg-emoji emoji-id='5431239810239106666'>💌</tg-emoji>"
# ROCKET_SHOCK = "<tg-emoji emoji-id='5431239810239107777'>🚀</tg-emoji>"
DOWN_ARROW = "<tg-emoji emoji-id='5879619686294887057'>👇</tg-emoji>"


CAUTION = "<tg-emoji emoji-id='5852988909079764129'>⚠️</tg-emoji>"
PRESENT = "<tg-emoji emoji-id='5879852520766970657'>🎁</tg-emoji>"
NEW_MESSAGE = "<tg-emoji emoji-id='5879574082332137741'>🔹</tg-emoji>"