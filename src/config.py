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

# ⚠️ بسیار مهم: برای رندر شدن صحیح در بخش اینلاین، حتماً مقدار emoji-id باید داخل دابل‌کوتیشن (") باشد.
EMOJI = {
    "whisper_wait" : '<tg-emoji emoji-id="5879791055489998105">📬</tg-emoji>',
    "whisper_read" : '<tg-emoji emoji-id="5879798279624990117">📭</tg-emoji>',
    "target" : '<tg-emoji emoji-id="5310278924616356636">🎯</tg-emoji>',
    "check" : '<tg-emoji emoji-id="5882153540905868842">✅</tg-emoji>',
    "trash" : '<tg-emoji emoji-id="5879496330539179820">🗑</tg-emoji>',
    "lock" : '<tg-emoji emoji-id="5879888933499706415">🔒</tg-emoji>',
    "block" : '<tg-emoji emoji-id="5852969637561507022">🚫</tg-emoji>',
    "ban" : '<tg-emoji emoji-id="5879969197848533131">❌</tg-emoji>',
    "light" : '<tg-emoji emoji-id="5879796677602187415">💡</tg-emoji>',
    "ball" : '<tg-emoji emoji-id="4958624886663678191">🔮</tg-emoji>',
    "id" : '<tg-emoji emoji-id="5879852112745077416">🆔</tg-emoji>',
    "mail" : '<tg-emoji emoji-id="5443127283898405358">📥</tg-emoji>',
    "down" : '<tg-emoji emoji-id="5879619686294887057">👇</tg-emoji>',
    "caution" : '<tg-emoji emoji-id="5852988909079764129">⚠️</tg-emoji>',
    "present" : '<tg-emoji emoji-id="5879852520766970657">🎁</tg-emoji>',
    "green_dot" : '<tg-emoji emoji-id="5879574082332137741">🔹</tg-emoji>',
    "profile" : '<tg-emoji emoji-id="5879763795332570363">👤</tg-emoji>',
    "magnifiyer" : '<tg-emoji emoji-id="5231012545799666522">🔍</tg-emoji>',
    "thunder" : '<tg-emoji emoji-id="5456140674028019486">⚡️</tg-emoji>',
    "update" : '<tg-emoji emoji-id="4956371914323920049">🔄</tg-emoji>',
    "ok" : '<tg-emoji emoji-id="4956649845952611245">🔄</tg-emoji>',
    "sus" : '<tg-emoji emoji-id="5253645558865756077">😁</tg-emoji>',
}

# LOVE_LETTER = '<tg-emoji emoji-id="5431239810239106666">💌</tg-emoji>'
# ROCKET_SHOCK = '<tg-emoji emoji-id="5431239810239107777">🚀</tg-emoji>'