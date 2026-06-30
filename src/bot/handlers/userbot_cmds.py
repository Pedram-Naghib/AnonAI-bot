"""
سمتِ «ربات رسمی» برای سیستم پخش موزیک در ویس‌چت (نسخهٔ بدون Redis).

نقش این ماژول:
  • گرفتن دستور «پخش» (ریپلای روی یک فایل صوتی) از سوپریوزرها
  • گرفتن دستور «پخش <اسم آهنگ>» و جست‌وجو/دانلود از یوتیوب (yt-dlp)
  • ساختن پنل فارسی با دکمه‌های شیشه‌ای هوشمند (پخش/توقف پویا) + نام و اطلاعات آهنگ
  • ریپلای‌کردنِ پنل به پیامِ فرستنده
  • دستورهای متنیِ «بعدی» و «پایان پخش» (فقط برای آغازگرِ پخش)
  • دستور «پنل» برای احضارِ دوبارهٔ پنلِ کنترل
  • چک کردن مجوز کلیک روی دکمه‌ها (فقط آغازگر یا سوپریوزرها)
  • فرستادن مستقیم دستورها به توابع یوزربات (بدون واسطهٔ Redis)
"""

import os
import html
import asyncio

from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.config import SUPER_USERS
from src.bot.music_protocol import get_now, get_queue_len
from src.bot.user_bot.music_bot import (
    cmd_play, cmd_pause, cmd_resume, cmd_skip, cmd_stop, repoint_panel,
    search_and_download_youtube,
)


# ── گروهی که اجازهٔ پخش در آن داده شده ─────────────────────
MUSIC_GROUP_ID = -1001434396268

# ── پیشوندهایی که دستورِ «پخش از یوتیوب» را فعال می‌کنند ──
_YT_PLAY_PREFIXES = ("پخش ", "/play ")


# ── کمک‌تابع: قالب‌بندیِ مدت‌زمان (ثانیه → mm:ss) ───────────
def _fmt_duration(seconds: int) -> str:
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ── خطِ «اطلاعاتِ آهنگ» (خواننده + مدت‌زمان) ────────────────
def _info_line(performer: str, duration: int) -> str:
    parts = []
    if performer:
        parts.append(f"👤 {html.escape(performer)}")
    dur = _fmt_duration(duration)
    if dur:
        parts.append(f"⏱ {dur}")
    return ("\n" + "   ".join(parts)) if parts else ""


# ── ساختِ متن و دکمه‌های پنل بر اساس وضعیت ─────────────────
def build_panel(state: str, title: str, queue_len: int,
                performer: str = "", duration: int = 0, with_video: bool = False):
    """
    خروجی: (متن HTML، کیبوردِ متناسب با وضعیت)
    وضعیت‌ها: playing | paused | idle
    دکمه‌ها هوشمندند؛ یعنی هنگام پخش فقط «توقف» و هنگام مکث فقط «ادامه» دیده می‌شود.
    حالا نامِ آهنگ + اطلاعاتِ آن (خواننده و مدت‌زمان) هم نمایش داده می‌شود.
    with_video=True یعنی محتوا به‌صورتِ ویدیو هم در ویس‌چت پخش می‌شود (نه فقط صدا).
    """
    safe_title = html.escape(title or "نامشخص")
    info       = _info_line(performer, duration)
    queue_line = f"\n\n📋 در صف: <b>{queue_len}</b> آهنگ" if queue_len > 0 else ""
    icon       = "🎬" if with_video else "🎧"

    if state == "playing":
        text = f"🎵 <b>در حال پخش</b>\n{icon} {safe_title}{info}{queue_line}"
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("⏸ توقف", callback_data="mus_pause", style="primary"),
            InlineKeyboardButton("⏭ بعدی", callback_data="mus_skip", style="success"),
        )
        kb.row(InlineKeyboardButton("⛔ پایان پخش", callback_data="mus_stop", style="danger"))
        return text, kb

    if state == "paused":
        text = f"⏸ <b>متوقف شده</b>\n{icon} {safe_title}{info}{queue_line}"
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


# ── رسیدِ «به صف اضافه شد» (جایگزینِ پیامِ «در حال اتصال…») ──
def build_queue_added(title: str, performer: str, duration: int, position: int) -> str:
    safe_title = html.escape(title or "نامشخص")
    info       = _info_line(performer, duration)
    return (
        f"➕ <b>به صف اضافه شد</b>\n🎧 {safe_title}{info}"
        f"\n\n📋 موقعیت در صف: <b>{position}</b>"
    )


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

    # ── دستور «پخش»: ریپلای روی فایل صوتی یا ویدیویی ──────
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
        if (user_id not in SUPER_USERS) and (chat_id != MUSIC_GROUP_ID):
            await bot.reply_to(message, "⛔ فقط مدیران اجازهٔ پخش موزیک دارند.")
            return

        # استخراجِ فایل صوتی/ویدیوییِ ریپلای‌شده + متادیتا (عنوان/خواننده/مدت)
        # video / video_note (پیام‌های ویدیوییِ گرد) / animation هم پشتیبانی می‌شوند —
        # در این حالت with_video=True می‌شود تا تصویر هم در ویس‌چت پخش شود.
        replied    = message.reply_to_message
        file_id    = None
        file_size  = 0
        performer  = ""
        duration   = 0
        with_video = False
        if replied.audio:
            title     = replied.audio.title or replied.audio.file_name or "آهنگ ناشناس"
            performer = replied.audio.performer or ""
            duration  = replied.audio.duration or 0
            file_id   = replied.audio.file_id
            file_size = replied.audio.file_size or 0
        elif replied.voice:
            title     = "پیام صوتی"
            duration  = replied.voice.duration or 0
            file_id   = replied.voice.file_id
            file_size = replied.voice.file_size or 0
        elif replied.video:
            title      = replied.video.file_name or "ویدیو"
            duration   = replied.video.duration or 0
            file_id    = replied.video.file_id
            file_size  = replied.video.file_size or 0
            with_video = True
        elif replied.video_note:
            title      = "پیام ویدیویی"
            duration   = replied.video_note.duration or 0
            file_id    = replied.video_note.file_id
            file_size  = replied.video_note.file_size or 0
            with_video = True
        elif replied.animation:
            title      = replied.animation.file_name or "گیف/انیمیشن"
            duration   = replied.animation.duration or 0
            file_id    = replied.animation.file_id
            file_size  = replied.animation.file_size or 0
            with_video = True
        elif replied.document and (replied.document.mime_type or "").startswith("audio"):
            title     = replied.document.file_name or "فایل صوتی"
            file_id   = replied.document.file_id
            file_size = replied.document.file_size or 0
        elif replied.document and (replied.document.mime_type or "").startswith("video"):
            title      = replied.document.file_name or "ویدیو"
            file_id    = replied.document.file_id
            file_size  = replied.document.file_size or 0
            with_video = True
        else:
            await bot.reply_to(message, "❗️ لطفاً روی یک فایل صوتی یا ویدیویی (آهنگ/ویس/ویدیو/پیام‌ویدیویی) ریپلای کنید.")
            return

        # ساختِ پنل اولیه — به‌صورتِ ریپلای به پیامِ فرستنده — تا آیدی آن را به یوزربات بدهیم
        kind = "ویدیو" if with_video else "موزیک"
        panel = await bot.reply_to(
            message,
            f"🔄 در حال اتصال به ویس‌چت برای پخش {kind} «{html.escape(title)}»...",
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
            performer=performer,
            duration=duration,
            with_video=with_video,
        ))

    # ── دستور «پخش <اسم آهنگ>»: جست‌وجو و دانلود از یوتیوب ──
    @bot.message_handler(
        func=lambda m: (
            m.chat.type in ("group", "supergroup")
            and m.text is not None
            and m.text.strip().startswith(_YT_PLAY_PREFIXES)
            and m.text.strip() not in ("پخش", "/play")  # خالی → برود سمتِ هندلرِ ریپلای بالا
        ),
        content_types=["text"],
    )
    async def handle_play_youtube_command(message):
        chat_id = message.chat.id
        user_id = message.from_user.id

        if (user_id not in SUPER_USERS) and (chat_id != MUSIC_GROUP_ID):
            await bot.reply_to(message, "⛔ فقط مدیران اجازهٔ پخش موزیک دارند.")
            return

        raw = message.text.strip()
        for prefix in _YT_PLAY_PREFIXES:
            if raw.startswith(prefix):
                query = raw[len(prefix):].strip()
                break
        else:
            query = ""

        if not query:
            await bot.reply_to(message, "❗️ بعد از «پخش» اسم آهنگ رو هم بنویس؛ مثلاً: «پخش shape of you».")
            return

        panel = await bot.reply_to(
            message,
            f"🔎 در حال جست‌وجوی «{html.escape(query)}» در یوتیوب...",
            parse_mode="HTML",
        )

        try:
            result = await search_and_download_youtube(query)
        except ValueError as e:
            reason = str(e)
            if reason.startswith("NO_RESULTS"):
                text = f"❌ چیزی برای «{html.escape(query)}» پیدا نشد."
            elif reason.startswith("YT_BOT_CHECK"):
                from src.bot.user_bot.music_bot import COOKIES_STATUS
                if COOKIES_STATUS == "invalid":
                    text = (
                        "🍪 فایلِ کوکیِ یوتیوب روی سرور خراب است (پارس نشد).\n"
                        "رایج‌ترین دلیل: تب‌های بینِ ستون‌ها هنگامِ پیست در Render "
                        "به اسپیس تبدیل شده‌اند. کوکی رو دوباره از مرورگر اکسپورت "
                        "کن و این‌بار با احتیاط (بدون ادیتورِ واسط) توی متغیرِ "
                        "YT_COOKIES_CONTENT در Render پیست کن.\n"
                        "فعلاً می‌تونی فایلِ صوتی رو مستقیم بفرستی و روش ریپلای "
                        "کنی و بنویسی «پخش»."
                    )
                elif COOKIES_STATUS == "ok":
                    text = (
                        "🤖 با اینکه کوکی معتبر است، یوتیوب همچنان این درخواست "
                        "رو ربات تشخیص داده.\n"
                        "این یعنی مشکل از فرمتِ کوکی نیست؛ احتمالاً یا کوکی "
                        "منقضی شده، یا حسابش به اندازهٔ کافی «قدیمی/معتبر» "
                        "نیست، یا (محتمل‌تر) آی‌پیِ سرورِ Render توسطِ یوتیوب "
                        "به‌طورِ کلی مسدود شده — که در این صورت حتی با کوکیِ "
                        "خوب هم گاهی جواب نمی‌دهد.\n"
                        "فعلاً می‌تونی فایلِ صوتی رو مستقیم بفرستی و روش ریپلای "
                        "کنی و بنویسی «پخش»."
                    )
                else:
                    text = (
                        "🤖 یوتیوب فعلاً اجازهٔ دانلود از سرور را نمی‌دهد "
                        "(تشخیص ربات).\n"
                        "این مشکلِ خودِ یوتیوب است، نه ربات — برای رفع، یک فایلِ "
                        "کوکیِ حسابِ یوتیوب باید روی سرور تنظیم شود.\n"
                        "فعلاً می‌تونی به‌جاش فایلِ صوتی رو مستقیم بفرستی و روش "
                        "ریپلای کنی و بنویسی «پخش»."
                    )
            else:
                text = f"⚠️ خطا در دانلود از یوتیوب:\n<code>{html.escape(reason[:200])}</code>"
            await bot.edit_message_text(text, chat_id, panel.message_id, parse_mode="HTML")
            return
        except Exception as e:
            print(f"💥 youtube play unexpected error: {e}")
            await bot.edit_message_text(
                "⚠️ خطای غیرمنتظره در جست‌وجوی یوتیوب.", chat_id, panel.message_id
            )
            return

        await bot.edit_message_text(
            f"🔄 در حال اتصال به ویس‌چت برای پخش «{html.escape(result['title'])}»...",
            chat_id, panel.message_id, parse_mode="HTML",
        )

        # نکته: audio_chat_id/audio_msg_id اینجا استفاده نمی‌شوند چون audio_path
        # از قبل توسط yt-dlp آماده شده — cmd_play همیشه اول audio_path را چک می‌کند.
        asyncio.create_task(cmd_play(
            chat_id=chat_id,
            audio_chat_id=chat_id,
            audio_msg_id=message.message_id,
            title=result["title"],
            requester_id=user_id,
            initiator_id=user_id,
            panel_msg_id=panel.message_id,
            audio_path=result["path"],
            performer=result["performer"],
            duration=result["duration"],
        ))

    # ── دستورهای متنی: «بعدی» و «پایان پخش» (فقط آغازگرِ پخش) ──
    @bot.message_handler(
        func=lambda m: (
            m.chat.type in ("group", "supergroup")
            and m.text is not None
            and m.text.strip() in ("بعدی", "پایان پخش", "/skip", "/stop")
        ),
        content_types=["text"],
    )
    async def handle_text_controls(message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        cmd     = message.text.strip()

        now = get_now(chat_id)
        if not now:
            await bot.reply_to(message, "🔇 الان چیزی در حال پخش نیست.")
            return

        # امنیت: فقط کسی که پخش را شروع کرده (یا سوپریوزر) اجازه دارد
        if not await _is_authorized(chat_id, user_id):
            await bot.reply_to(message, "⛔ فقط کسی که پخش را شروع کرده می‌تواند این کار را انجام دهد.")
            return

        if cmd in ("بعدی", "/skip"):
            asyncio.create_task(cmd_skip(chat_id))
            await bot.reply_to(message, "⏭ رفتم سراغ آهنگِ بعدیِ صف.")
        else:  # «پایان پخش» یا /stop
            asyncio.create_task(cmd_stop(chat_id))
            await bot.reply_to(message, "⛔ پخش متوقف شد و از ویس‌چت خارج می‌شوم.")

    # ── دستور «پنل»: احضارِ دوبارهٔ پنلِ کنترل (ریپلای به فرستنده) ──
    @bot.message_handler(
        func=lambda m: (
            m.chat.type in ("group", "supergroup")
            and m.text is not None
            and m.text.strip() in ("پنل", "/panel")
        ),
        content_types=["text"],
    )
    async def handle_panel_command(message):
        chat_id = message.chat.id

        now = get_now(chat_id)
        if not now:
            await bot.reply_to(message, "🔇 الان چیزی در حال پخش نیست تا پنلی نشان دهم.")
            return

        text, kb = build_panel(
            now.get("state", "idle"),
            now.get("title", ""),
            get_queue_len(chat_id),
            now.get("performer", ""),
            now.get("duration", 0),
            now.get("with_video", False),
        )
        sent = await bot.reply_to(message, text, parse_mode="HTML", reply_markup=kb)
        # از این به بعد، آپدیت‌های موتورِ موزیک روی همین پیامِ تازه انجام می‌شود.
        repoint_panel(chat_id, sent.message_id)

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