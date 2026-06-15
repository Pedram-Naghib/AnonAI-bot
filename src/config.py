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
    "whisper_wait" : '<tg-emoji emoji-id="5868195356755370111">📬</tg-emoji>',
    "whisper_read" : '<tg-emoji emoji-id="5868445959507156108">📭</tg-emoji>',
    "target" : '<tg-emoji emoji-id="5868616216305738579">🎯</tg-emoji>',
    "check" : '<tg-emoji emoji-id="5868702253090611120">✅</tg-emoji>',
    "trash" : '<tg-emoji emoji-id="5870613728285697092">🗑</tg-emoji>',
    "lock" : '<tg-emoji emoji-id="5868221281177969106">🔒</tg-emoji>',
    "block" : '<tg-emoji emoji-id="5868508339612163226">🚫</tg-emoji>',
    "ban" : '<tg-emoji emoji-id="5868433319418404056">❌</tg-emoji>',
    "light" : '<tg-emoji emoji-id="5868625484845163063">💡</tg-emoji>',
    "ball" : '<tg-emoji emoji-id="5870699069285868279">🔮</tg-emoji>',
    "id" : '<tg-emoji emoji-id="5870497545125371625">🆔</tg-emoji>',
    "recieve" : '<tg-emoji emoji-id="5868240462501912848">📥</tg-emoji>',
    "send" : '<tg-emoji emoji-id="5870715072334012530">📤</tg-emoji>',
    "down" : '<tg-emoji emoji-id="5870729151236807884">👇</tg-emoji>',
    "up" : '<tg-emoji emoji-id="5868527134389050697">👆</tg-emoji>',
    "caution" : '<tg-emoji emoji-id="5868555403863793670">⚠️</tg-emoji>',
    "present" : '<tg-emoji emoji-id="5868604173217439631">🎁</tg-emoji>',
    "green_dot" : '<tg-emoji emoji-id="5868523346227895435">🔹</tg-emoji>',
    "red_dot" : '<tg-emoji emoji-id="5868329449929319325">🔹</tg-emoji>',
    "profile" : '<tg-emoji emoji-id="5868399268917682484">👤</tg-emoji>',
    "magnifiyer" : '<tg-emoji emoji-id="5868558887082270806">🔍</tg-emoji>',
    "thunder" : '<tg-emoji emoji-id="5868452208684572648">⚡️</tg-emoji>',
    "update" : '<tg-emoji emoji-id="5868508666029677559">🔄</tg-emoji>',
    "ok" : '<tg-emoji emoji-id="5870571865239461711">👍</tg-emoji>',
    "like" : '<tg-emoji emoji-id=""5870869832890590154"">👍</tg-emoji>',
    "dislike" : '<tg-emoji emoji-id="5868682526305820930">👎</tg-emoji>',
    "fuck" : '<tg-emoji emoji-id="5868688470540558068">🖕</tg-emoji>',
    "nerd" : '<tg-emoji emoji-id=""5870769966311022631"">🤓</tg-emoji>',
    "sus" : '<tg-emoji emoji-id="5868342588234277601">😁</tg-emoji>',
    "plus" : '<tg-emoji emoji-id="5868629260121415108">➕</tg-emoji>',
    "gem" : '<tg-emoji emoji-id="5870799867873336170">💎</tg-emoji>',
    "100" : '<tg-emoji emoji-id="5868666441653297911">💯</tg-emoji>',
    "web" : '<tg-emoji emoji-id="5870461634903809731">🖥</tg-emoji>',
    "link" : '<tg-emoji emoji-id="5870840446724349768">🔗</tg-emoji>',
    "shield" : '<tg-emoji emoji-id="5870958210432639067">🛡</tg-emoji>',
    "secret" : '<tg-emoji emoji-id="5868602300611698325">🤫</tg-emoji>',
    "fire" : '<tg-emoji emoji-id="5868693302378765752">🔥</tg-emoji>',
    "pin" : '<tg-emoji emoji-id="5868440964460191170">📌</tg-emoji>',
    "cloud" : '<tg-emoji emoji-id="5868645456443088810">💭</tg-emoji>',
    "chat" : '<tg-emoji emoji-id="5868620253574999713">💬</tg-emoji>',
    "bang" : '<tg-emoji emoji-id="5870958210432639067">💥</tg-emoji>',
    "red_thunder" : '<tg-emoji emoji-id="5870769747267690165">☄️</tg-emoji>',
    "eyes" : '<tg-emoji emoji-id="5872695374380015050">👀</tg-emoji>',
    "setting" : '<tg-emoji emoji-id="5870541160518261812">⚙️</tg-emoji>',
    "red_caution" : '<tg-emoji emoji-id="5872855774228651803">📛</tg-emoji>',
    "banned" : '<tg-emoji emoji-id="5872876536100560928">⛔</tg-emoji>',
    "right" : '<tg-emoji emoji-id="5873026116926577026">👉</tg-emoji>',
    "left" : '<tg-emoji emoji-id="5872874745099197560">👈</tg-emoji>',
    "qe" : '<tg-emoji emoji-id="5873170659755957379">⁉️</tg-emoji>',
    "exc" : '<tg-emoji emoji-id="5872998702150327568">❗️</tg-emoji>',
    "question" : '<tg-emoji emoji-id="5870477268584767271">❓</tg-emoji>',
    "clock" : '<tg-emoji emoji-id="5872734153639730784">⏳</tg-emoji>',
    "one" : '<tg-emoji emoji-id="5872823033692953756">1️⃣</tg-emoji>',
    "two" : '<tg-emoji emoji-id="5870919482712531389">2️⃣</tg-emoji>',
    "three" : '<tg-emoji emoji-id="5873253681473788956">3️⃣</tg-emoji>',
    "crcl_no" : '<tg-emoji emoji-id="5872955666578022411">✖️</tg-emoji>',
    "crcl_yes" : '<tg-emoji emoji-id="5873104109237706731">✔️</tg-emoji>',
    "coin" : '<tg-emoji emoji-id="5872982376979636091">💰</tg-emoji>',
    "bot" : '<tg-emoji emoji-id="5872875896150432628">🤖</tg-emoji>',
    "mail" : '<tg-emoji emoji-id="5872780380372737109">📨</tg-emoji>',
}

# LOVE_LETTER = '<tg-emoji emoji-id="5431239810239106666">💌</tg-emoji>'
# ROCKET_SHOCK = '<tg-emoji emoji-id="5431239810239107777">🚀</tg-emoji>'