"""
پل ارتباطی Redis بین «ربات رسمی» (Telebot) و «یوزربات موزیک» (Telethon + PyTgCalls).

این فایل فقط نام کانال‌ها و کلیدها و چند هِلپر سریالایز را نگه می‌دارد تا هر دو
پروسه دقیقاً از یک قرارداد استفاده کنند و هیچ‌وقت از هم جدا نیفتند (drift).

جریان کلی:
  ربات رسمی ──(دستور)──►  music:commands  ──►  یوزربات
  یوزربات   ──(رویداد)─►  music:events    ──►  ربات رسمی (ادیت پنل/دکمه‌ها)

داده‌ها:
  music_now:{chat_id}    → یک JSON از آهنگ در حال پخش + وضعیت + آیدی پنل + آغازگر
  music_queue:{chat_id}  → یک LIST از آهنگ‌های در صف (هر آیتم JSON، فقط با آیدیِ پیام)
"""

import json

# ── کانال‌های Pub/Sub ─────────────────────────────────────
CMD_CHANNEL = "music:commands"   # ربات رسمی → یوزربات
EVT_CHANNEL = "music:events"     # یوزربات → ربات رسمی

# ── مدت بیکاری مجاز پیش از خروج خودکار (ثانیه) ─────────────
IDLE_TIMEOUT = 180  # ۳ دقیقه


# ── سازندهٔ کلیدها ────────────────────────────────────────
def now_key(chat_id: int) -> str:
    return f"music_now:{chat_id}"


def queue_key(chat_id: int) -> str:
    return f"music_queue:{chat_id}"


# ── هِلپرهای سریالایز ─────────────────────────────────────
def pack(payload: dict) -> str:
    """تبدیل دیکشنری به رشتهٔ JSON برای ارسال روی کانال."""
    return json.dumps(payload, ensure_ascii=False)


def unpack(raw) -> dict:
    """خواندن امنِ JSON دریافتی؛ در صورت خرابی، دیکشنری خالی."""
    try:
        return json.loads(raw)
    except Exception:
        return {}