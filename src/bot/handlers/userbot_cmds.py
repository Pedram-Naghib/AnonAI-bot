"""
سمتِ «ربات رسمی» برای سیستم پخش موزیک در ویس‌چت (نسخهٔ بدون Redis).

نقش این ماژول:
  • گرفتن دستور «پخش» (ریپلای روی یک فایل صوتی) از سوپریوزرها
  • ساختن پنل فارسی با دکمه‌های شیشه‌ای هوشمند (پخش/توقف پویا)
  • چک کردن مجوز کلیک روی دکمه‌ها (فقط آغازگر یا سوپریوزرها)
  • فرستادن مستقیم دستورها به توابع یوزربات (بدون واسطهٔ Redis)
"""

import os
import html
import asyncio

from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.config import SUPER_USERS
from src.bot.music_protocol import get_now
from src.bot.user_bot.music_bot import cmd_play, cmd_pause, cmd_resume, cmd_skip, cmd_stop

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
            InlineKeyboardButton("⏸ توقف", callback_data="mus_pause", style="primary"),
            InlineKeyboardButton("⏭ بعدی", callback_data="mus_skip", style="success"),
        )
        kb.row(InlineKeyboardButton("⛔ پایان پخش", callback_data="mus_stop", style="danger"))
        return text, kb

    if state == "paused":
        text = f"⏸ <b>متوقف شده</b>\n🎧 {safe_title}{queue_line}"
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("▶️ ادامه", callback_data="mus_resume", style="primary"),
            InlineKeyboardButton("⏭ بعدی", callback_data="mus_skip", style="success"),
        )
        kb.row(InlineKeyboardButton("⛔ پایان پخش", callback_data="mus_stop", style="danger"))
        return text, kb

    # idle / پایان‌یافته
    text = "✅ <b>پخش به پایان رسید.</b>\nاگر تا چند دقیقه آهنگی پخش نشود، از ویس‌چت خارج می‌شوم."
    return text, None


# ── چک مجوز: فقط آغازگر یا سوپریوزرها ─────────────────────
async def _is_authorized(chat_id: int, user_id: int) -> bool:
    if user_id in SUPER_USERS:
        return True
    try:
        # 🌟 خواندن مستقیم وضعیت فعلی از RAM به جای Redis
        data = get_now(chat_id)
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
        if (user_id not in SUPER_USERS) and (chat_id != -1001434396268):
            await bot.reply_to(message, "⛔ فقط مدیران اجازهٔ پخش موزیک دارند.")
            return

        # استخراجِ فایل صوتیِ ریپلای‌شده + file_id برای دانلودِ سمتِ ربات
        replied   = message.reply_to_message
        file_id   = None
        file_size = 0
        if replied.audio:
            title     = replied.audio.title or replied.audio.file_name or "آهنگ ناشناس"
            file_id   = replied.audio.file_id
            file_size = replied.audio.file_size or 0
        elif replied.voice:
            title     = "پیام صوتی"
            file_id   = replied.voice.file_id
            file_size = replied.voice.file_size or 0
        elif replied.document and (replied.document.mime_type or "").startswith("audio"):
            title     = replied.document.file_name or "فایل صوتی"
            file_id   = replied.document.file_id
            file_size = replied.document.file_size or 0
        else:
            await bot.reply_to(message, "❗️ لطفاً روی یک فایل صوتی (آهنگ/ویس) ریپلای کنید.")
            return

        # ساختِ پنل اولیه (در همان گروه) تا آیدی آن را به یوزربات بدهیم
        panel = await bot.send_message(
            chat_id,
            f"🔄 در حال اتصال به ویس‌چت برای پخش «{html.escape(title)}»...",
            parse_mode="HTML",
        )

        # 🌟 دانلودِ فایل توسطِ خودِ ربات رسمی (مطمئن‌ترین راه؛ بدون وابستگی به
        # خواندنِ پیام از سمت یوزربات که گاهی MESSAGE_NOT_FOUND می‌داد).
        # محدودیتِ Bot API برای دانلود ۲۰ مگابایت است؛ اگر بزرگ‌تر بود،
        # local_path خالی می‌ماند و یوزربات خودش فالبک می‌زند.
        local_path = None
        BOT_DL_LIMIT = 20 * 1024 * 1024
        if file_id and (file_size == 0 or file_size <= BOT_DL_LIMIT):
            try:
                os.makedirs("downloads", exist_ok=True)
                finfo = await bot.get_file(file_id)
                data  = await bot.download_file(finfo.file_path)
                ext   = os.path.splitext(finfo.file_path or "")[1] or ".audio"
                local_path = os.path.join("downloads", f"{chat_id}_{replied.message_id}{ext}")
                with open(local_path, "wb") as f:
                    f.write(data)
            except Exception as e:
                print(f"⚠️ bot-side download failed ({e}); falling back to userbot fetch.")
                local_path = None

        # 🌟 فراخوانی مستقیم تابع پخش یوزربات به صورت تسک پس‌زمینه
        asyncio.create_task(cmd_play(
            chat_id=chat_id,
            audio_chat_id=chat_id,
            audio_msg_id=replied.message_id,
            title=title,
            requester_id=user_id,
            initiator_id=user_id,
            panel_msg_id=panel.message_id,
            audio_path=local_path,
        ))

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

        labels = {"pause": "توقف شد", "resume": "ادامه یافت", "skip": "آهنگ بعدی", "stop": "پخش پایان یافت"}
        
        # 🌟 هدایت مستقیم اکشن‌ها به توابع موتور موزیک
        if action == "pause":
            asyncio.create_task(cmd_pause(chat_id))
        elif action == "resume":
            asyncio.create_task(cmd_resume(chat_id))
        elif action == "skip":
            asyncio.create_task(cmd_skip(chat_id))
        elif action == "stop":
            asyncio.create_task(cmd_stop(chat_id))

        await bot.answer_callback_query(call.id, f"✅ {labels.get(action, 'انجام شد')}")

    print("🎵 Userbot music bridge handlers registered.")


async def start_music_event_listener(bot: AsyncTeleBot):
    """
    [DEPRECATED] این تابع در معماری جدید درون‌حافظه‌ای دیگر کاربردی ندارد
    چون یوزربات مستقیماً پنل‌ها را ویرایش می‌کند. صرفاً جهت جلوگیری از ImportError در main.py باقی مانده است.
    """
    print("🌙 Music event listener (In-Memory Mode) initialized natively.")
    while True:
        await asyncio.sleep(3600)