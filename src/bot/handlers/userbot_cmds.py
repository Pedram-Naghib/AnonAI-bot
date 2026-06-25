"""
سمتِ «ربات رسمی» برای سیستم پخش موزیک در ویس‌چت.

نقش این ماژول:
  • گرفتن دستور «پخش» (ریپلای روی یک فایل صوتی) از سوپریوزرها
  • ساختن پنل فارسی با دکمه‌های شیشه‌ای هوشمند (پخش/توقف پویا)
  • چک کردن مجوز کلیک روی دکمه‌ها (فقط آغازگر یا سوپریوزرها)
  • فرستادن دستورها به یوزربات از طریق Redis
  • گوش دادن به رویدادهای یوزربات و ادیتِ پنل/دکمه‌ها

نکته: چون یوزربات (Telethon) نمی‌تواند دکمهٔ شیشه‌ای بسازد، تمام رندرِ پیام و
دکمه‌ها بر عهدهٔ همین ربات رسمی است؛ یوزربات فقط «وضعیت» را اعلام می‌کند.
"""

import html

from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.config import SUPER_USERS
from src.bot.redis_config import redis_client
from src.bot.music_protocol import (
    CMD_CHANNEL, EVT_CHANNEL, now_key, pack, unpack,
)


# ── ساختِ متن و دکمه‌های پنل بر اساس وضعیت ─────────────────
def build_panel(state: str, title: str, queue_len: int):
    """
    خروجی: (متن HTML، کیبوردِ متناسب با وضعیت)
    وضعیت‌ها: playing | paused | idle
    دکمه‌ها هوشمندند؛ یعنی هنگام پخش فقط «توقف» و هنگام مکث فقط «ادامه» دیده می‌شود.
    """
    safe_title = html.escape(title or "نامشخص")
    queue_line = f"\n\n📋 در صف: <b>{queue_len}</b> آهنگ" if queue_len > 0 else ""

    if state == "playing":
        text = f"🎵 <b>در حال پخش</b>\n🎧 {safe_title}{queue_line}"
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("⏸ توقف", callback_data="mus_pause"),
            InlineKeyboardButton("⏭ بعدی", callback_data="mus_skip"),
        )
        kb.row(InlineKeyboardButton("⛔ پایان پخش", callback_data="mus_stop"))
        return text, kb

    if state == "paused":
        text = f"⏸ <b>متوقف شده</b>\n🎧 {safe_title}{queue_line}"
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("▶️ ادامه", callback_data="mus_resume"),
            InlineKeyboardButton("⏭ بعدی", callback_data="mus_skip"),
        )
        kb.row(InlineKeyboardButton("⛔ پایان پخش", callback_data="mus_stop"))
        return text, kb

    # idle / پایان‌یافته
    text = "✅ <b>پخش به پایان رسید.</b>\nاگر تا چند دقیقه آهنگی پخش نشود، از ویس‌چت خارج می‌شوم."
    return text, None


# ── چک مجوز: فقط آغازگر یا سوپریوزرها ─────────────────────
async def _is_authorized(chat_id: int, user_id: int) -> bool:
    if user_id in SUPER_USERS:
        return True
    if not redis_client:
        return False
    try:
        raw = await redis_client.get(now_key(chat_id))
        data = unpack(raw) if raw else {}
        return data.get("initiator_id") == user_id
    except Exception:
        return False


def register_userbot_handlers(bot: AsyncTeleBot):

    # ── دستور «پخش»: ریپلای روی فایل صوتی ─────────────────
    @bot.message_handler(
        func=lambda m: (
            m.chat.type in ("group", "supergroup")
            and m.text is not None
            and m.text.strip() in ("پخش", "/play")
            and m.reply_to_message is not None
        ),
        content_types=["text"],
    )
    async def handle_play_command(message):
        chat_id = message.chat.id
        user_id = message.from_user.id

        # امنیت: فقط سوپریوزرها اجازهٔ شروع پخش دارند
        if user_id not in SUPER_USERS:
            await bot.reply_to(message, "⛔ فقط مدیران اجازهٔ پخش موزیک دارند.")
            return

        if not redis_client:
            await bot.reply_to(message, "⚠️ موتور موزیک در دسترس نیست (Redis قطع است).")
            return

        # استخراجِ فایل صوتیِ ریپلای‌شده (فقط با آیدیِ پیام؛ بدون ذخیرهٔ فایل)
        replied = message.reply_to_message
        if replied.audio:
            title = replied.audio.title or replied.audio.file_name or "آهنگ ناشناس"
        elif replied.voice:
            title = "پیام صوتی"
        elif replied.document and (replied.document.mime_type or "").startswith("audio"):
            title = replied.document.file_name or "فایل صوتی"
        else:
            await bot.reply_to(message, "❗️ لطفاً روی یک فایل صوتی (آهنگ/ویس) ریپلای کنید.")
            return

        # ساختِ پنل اولیه (در همان گروه) تا آیدی آن را به یوزربات بدهیم
        panel = await bot.send_message(
            chat_id,
            f"🔄 در حال اتصال به ویس‌چت برای پخش «{html.escape(title)}»...",
            parse_mode="HTML",
        )

        # ارسال دستور پخش به یوزربات
        await redis_client.publish(CMD_CHANNEL, pack({
            "action":        "play",
            "chat_id":       chat_id,
            "audio_chat_id": chat_id,            # فایل در همین گروه است
            "audio_msg_id":  replied.message_id, # فقط آیدیِ پیام را می‌فرستیم
            "title":         title,
            "requester_id":  user_id,
            "initiator_id":  user_id,
            "panel_msg_id":  panel.message_id,
        }))

    # ── کال‌بکِ دکمه‌های پنل ───────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("mus_"))
    async def handle_music_buttons(call):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        action  = call.data.split("mus_")[-1]  # pause | resume | skip | stop

        # امنیت: کلیک فقط برای آغازگر یا سوپریوزر
        if not await _is_authorized(chat_id, user_id):
            await bot.answer_callback_query(
                call.id, "⛔ این پنل برای شما نیست!", show_alert=True
            )
            return

        if not redis_client:
            await bot.answer_callback_query(call.id, "⚠️ موتور موزیک در دسترس نیست.", show_alert=True)
            return

        labels = {"pause": "توقف شد", "resume": "ادامه یافت", "skip": "آهنگ بعدی", "stop": "پخش پایان یافت"}
        await redis_client.publish(CMD_CHANNEL, pack({"action": action, "chat_id": chat_id}))
        await bot.answer_callback_query(call.id, f"✅ {labels.get(action, 'انجام شد')}")

    print("🎵 Userbot music bridge handlers registered.")


# ── شنوندهٔ رویدادهای یوزربات (ادیتِ پنل/دکمه‌ها) ──────────
async def start_music_event_listener(bot: AsyncTeleBot):
    """
    در یک تسکِ پس‌زمینه روی کانال رویدادها می‌نشیند و هر تغییر وضعیت را
    روی پنلِ مربوطه اعمال می‌کند. این تنها مسیرِ به‌روزرسانی دکمه‌هاست.
    """
    if not redis_client:
        print("⚠️ Music event listener disabled — Redis not connected.")
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(EVT_CHANNEL)
    print("👂 Music event listener active.")

    async for raw in pubsub.listen():
        if raw.get("type") != "message":
            continue
        try:
            evt = unpack(raw["data"])
            kind = evt.get("event")

            if kind == "panel":
                # رندرِ مجددِ پنل بر اساس وضعیت گزارش‌شدهٔ یوزربات
                text, kb = build_panel(
                    evt.get("state", "idle"),
                    evt.get("title", ""),
                    int(evt.get("queue_len", 0)),
                )
                try:
                    await bot.edit_message_text(
                        text, evt["chat_id"], evt["panel_msg_id"],
                        parse_mode="HTML", reply_markup=kb,
                    )
                except Exception:
                    pass  # «message is not modified» و موارد مشابه را بی‌خیال می‌شویم

            elif kind == "toast":
                # یک پیام کوتاهِ اطلاع‌رسانی در گروه (مثلاً «به صف اضافه شد»)
                try:
                    await bot.send_message(evt["chat_id"], evt.get("text", ""), parse_mode="HTML")
                except Exception:
                    pass

        except Exception as e:
            print(f"💥 Music event listener error: {e}")