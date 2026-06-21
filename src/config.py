import os
from dotenv import load_dotenv

load_dotenv()

# ── Credentials ──────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY")
FERNET_KEY         = os.getenv("FERNET_KEY", "").encode()  # used by crypto.py

# ── IDs (centralised — import from here, never redefine) ─
GOD_ID        = int(os.getenv("GOD_ID", "6779908406"))
SUPER_USERS   = [int(x) for x in os.getenv("SUPER_USERS", "8627765327,6779908406").split(",")]
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-1001434396268"))
LOG_GROUP_ID  = int(os.getenv("LOG_GROUP_ID",  "-5295499371"))

# ── Deployment ───────────────────────────────────────────
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "anonai-bot.onrender.com")

# ── Startup validation ───────────────────────────────────
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

# ── Emoji map (html tag + plain char) ────────────────────
EMOJI = {
    "whisper_wait":  {"html": '<tg-emoji emoji-id="5868195356755370111">📬</tg-emoji>', "char": "📬"},
    "whisper_read":  {"html": '<tg-emoji emoji-id="5868445959507156108">📭</tg-emoji>', "char": "📭"},
    "target":        {"html": '<tg-emoji emoji-id="5868616216305738579">🎯</tg-emoji>', "char": "🎯"},
    "check":         {"html": '<tg-emoji emoji-id="5868702253090611120">✅</tg-emoji>', "char": "✅"},
    "trash":         {"html": '<tg-emoji emoji-id="5870613728285697092">🗑</tg-emoji>',  "char": "🗑"},
    "lock":          {"html": '<tg-emoji emoji-id="5868221281177969106">🔒</tg-emoji>', "char": "🔒"},
    "block":         {"html": '<tg-emoji emoji-id="5868508339612163226">🚫</tg-emoji>', "char": "🚫"},
    "ban":           {"html": '<tg-emoji emoji-id="5868433319418404056">❌</tg-emoji>', "char": "❌"},
    "light":         {"html": '<tg-emoji emoji-id="5868625484845163063">💡</tg-emoji>', "char": "💡"},
    "ball":          {"html": '<tg-emoji emoji-id="5870699069285868279">🔮</tg-emoji>', "char": "🔮"},
    "id":            {"html": '<tg-emoji emoji-id="5870497545125371625">🆔</tg-emoji>', "char": "🆔"},
    "recieve":       {"html": '<tg-emoji emoji-id="5868240462501912848">📥</tg-emoji>', "char": "📥"},
    "send":          {"html": '<tg-emoji emoji-id="5870715072334012530">📤</tg-emoji>', "char": "📤"},
    "down":          {"html": '<tg-emoji emoji-id="5870729151236807884">👇</tg-emoji>', "char": "👇"},
    "up":            {"html": '<tg-emoji emoji-id="5868527134389050697">👆</tg-emoji>', "char": "👆"},
    "caution":       {"html": '<tg-emoji emoji-id="5868555403863793670">⚠️</tg-emoji>', "char": "⚠️"},
    "present":       {"html": '<tg-emoji emoji-id="5868604173217439631">🎁</tg-emoji>', "char": "🎁"},
    "green_dot":     {"html": '<tg-emoji emoji-id="5868523346227895435">🔹</tg-emoji>', "char": "🔹"},
    "red_dot":       {"html": '<tg-emoji emoji-id="5868329449929319325">🔹</tg-emoji>', "char": "🔹"},
    "profile":       {"html": '<tg-emoji emoji-id="5868399268917682484">👤</tg-emoji>', "char": "👤"},
    "magnifiyer":    {"html": '<tg-emoji emoji-id="5868558887082270806">🔍</tg-emoji>', "char": "🔍"},
    "thunder":       {"html": '<tg-emoji emoji-id="5868452208684572648">⚡️</tg-emoji>', "char": "⚡️"},
    "update":        {"html": '<tg-emoji emoji-id="5868508666029677559">🔄</tg-emoji>', "char": "🔄"},
    "ok":            {"html": '<tg-emoji emoji-id="5870571865239461711">👍</tg-emoji>', "char": "👍"},
    "like":          {"html": '<tg-emoji emoji-id="5870869832890590154">👍</tg-emoji>', "char": "👍"},
    "dislike":       {"html": '<tg-emoji emoji-id="5868682526305820930">👎</tg-emoji>', "char": "👎"},
    "fuck":          {"html": '<tg-emoji emoji-id="5868688470540558068">🖕</tg-emoji>', "char": "🖕"},
    "nerd":          {"html": '<tg-emoji emoji-id="5870769966311022631">🤓</tg-emoji>', "char": "🤓"},
    "sus":           {"html": '<tg-emoji emoji-id="5868342588234277601">😁</tg-emoji>', "char": "😁"},
    "plus":          {"html": '<tg-emoji emoji-id="5868629260121415108">➕</tg-emoji>', "char": "➕"},
    "gem":           {"html": '<tg-emoji emoji-id="5870799867873336170">💎</tg-emoji>', "char": "💎"},
    "100":           {"html": '<tg-emoji emoji-id="5868666441653297911">💯</tg-emoji>', "char": "💯"},
    "web":           {"html": '<tg-emoji emoji-id="5870461634903809731">🖥</tg-emoji>',  "char": "🖥"},
    "link":          {"html": '<tg-emoji emoji-id="5870840446724349768">🔗</tg-emoji>', "char": "🔗"},
    "shield":        {"html": '<tg-emoji emoji-id="5870958210432639067">🛡</tg-emoji>',  "char": "🛡"},
    "secret":        {"html": '<tg-emoji emoji-id="5868602300611698325">🤫</tg-emoji>', "char": "🤫"},
    "fire":          {"html": '<tg-emoji emoji-id="5868693302378765752">🔥</tg-emoji>', "char": "🔥"},
    "pin":           {"html": '<tg-emoji emoji-id="5868440964460191170">📌</tg-emoji>', "char": "📌"},
    "cloud":         {"html": '<tg-emoji emoji-id="5868645456443088810">💭</tg-emoji>', "char": "💭"},
    "chat":          {"html": '<tg-emoji emoji-id="5868620253574999713">💬</tg-emoji>', "char": "💬"},
    "bang":          {"html": '<tg-emoji emoji-id="5870958210432639067">💥</tg-emoji>', "char": "💥"},
    "red_thunder":   {"html": '<tg-emoji emoji-id="5870769747267690165">☄️</tg-emoji>', "char": "☄️"},
    "eyes":          {"html": '<tg-emoji emoji-id="5872695374380015050">👀</tg-emoji>', "char": "👀"},
    "setting":       {"html": '<tg-emoji emoji-id="5870541160518261812">⚙️</tg-emoji>', "char": "⚙️"},
    "red_caution":   {"html": '<tg-emoji emoji-id="5872855774228651803">📛</tg-emoji>', "char": "📛"},
    "banned":        {"html": '<tg-emoji emoji-id="5872876536100560928">⛔</tg-emoji>', "char": "⛔"},
    "right":         {"html": '<tg-emoji emoji-id="5873026116926577026">👉</tg-emoji>', "char": "👉"},
    "left":          {"html": '<tg-emoji emoji-id="5872874745099197560">👈</tg-emoji>', "char": "👈"},
    "qe":            {"html": '<tg-emoji emoji-id="5873170659755957379">⁉️</tg-emoji>', "char": "⁉️"},
    "exc":           {"html": '<tg-emoji emoji-id="5872998702150327568">❗️</tg-emoji>', "char": "❗️"},
    "question":      {"html": '<tg-emoji emoji-id="5870477268584767271">❓</tg-emoji>', "char": "❓"},
    "clock":         {"html": '<tg-emoji emoji-id="5872734153639730784">⏳</tg-emoji>', "char": "⏳"},
    "one":           {"html": '<tg-emoji emoji-id="5872823033692953756">1️⃣</tg-emoji>', "char": "1️⃣"},
    "two":           {"html": '<tg-emoji emoji-id="5870919482712531389">2️⃣</tg-emoji>', "char": "2️⃣"},
    "three":         {"html": '<tg-emoji emoji-id="5873253681473788956">3️⃣</tg-emoji>', "char": "3️⃣"},
    "four":          {"html": '<tg-emoji emoji-id="5873142974396767904">4️⃣</tg-emoji>', "char": "4️⃣"},
    "five":          {"html": '<tg-emoji emoji-id="5872804406419791932">5️⃣</tg-emoji>', "char": "5️⃣"},
    "six":           {"html": '<tg-emoji emoji-id="5870843440316554789">6️⃣</tg-emoji>', "char": "6️⃣"},
    "crcl_no":       {"html": '<tg-emoji emoji-id="5872955666578022411">✖️</tg-emoji>', "char": "✖️"},
    "crcl_yes":      {"html": '<tg-emoji emoji-id="5873104109237706731">✔️</tg-emoji>', "char": "✔️"},
    "coin":          {"html": '<tg-emoji emoji-id="5872982376979636091">💰</tg-emoji>', "char": "💰"},
    "bot":           {"html": '<tg-emoji emoji-id="5872875896150432628">🤖</tg-emoji>', "char": "🤖"},
    "mail":          {"html": '<tg-emoji emoji-id="5872780380372737109">📨</tg-emoji>', "char": "📨"},
}

# ── Userbot Creditentials ───────────────────────────────────
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")