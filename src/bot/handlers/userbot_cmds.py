"""
سمتِ «ربات رسمی» برای سیستم پخش موزیک در ویس‌چت.

قابلیت‌ها:
  • پخش ریپلای روی فایل صوتی/ویدیویی
  • هاب با دکمه‌های شیشه‌ای: توقف/ادامه/بعدی/پایان/shuffle/loop/ولوم/لیست/بستن
  • لایک ❤️ / دیسلایک ❌ روی هاب (ذخیره در DB)
  • دستور «علاقه‌مندی‌ها» برای صف کردن آهنگ‌های لایک‌شده در همین گروه
  • دستور «تاریخچه» برای دیدن آخرین آهنگ‌های پخش‌شده
  • «پخش بعدی این باشه» روی پیام اضافه‌شدن به صف
"""

import os
import html
import asyncio

from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.config import SUPER_USERS
from src.bot.music_protocol import (
    get_now, get_queue_len, peek_queue, get_history,
    get_loop, get_volume, VOLUME_STEP, LOOP_NONE, LOOP_TRACK, LOOP_QUEUE,
)
from src.bot.user_bot.music_bot import (
    cmd_play, cmd_pause, cmd_resume, cmd_skip, cmd_stop,
    cmd_shuffle, cmd_loop, cmd_volume, cmd_mute, cmd_move_to_front,
    repoint_panel,
)


MUSIC_GROUP_ID = -1001434396268

_LOOP_ICONS = {LOOP_NONE: "🔁", LOOP_TRACK: "🔂", LOOP_QUEUE: "🔁✅"}
_LOOP_LABELS = {
    LOOP_NONE:  "🔁 لوپ: خاموش",
    LOOP_TRACK: "🔂 لوپ: یک آهنگ",
    LOOP_QUEUE: "🔁 لوپ: همه صف",
}


# ════════════════════════════════════════════════════════════
#  کمک‌توابع
# ════════════════════════════════════════════════════════════
def _fmt_duration(seconds: int) -> str:
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _info_line(performer: str, duration: int) -> str:
    parts = []
    if performer:
        parts.append(f"👤 {html.escape(performer)}")
    dur = _fmt_duration(duration)
    if dur:
        parts.append(f"⏱ {dur}")
    return ("\n" + "   ".join(parts)) if parts else ""


def _requester_line(requester_id: int, requester_name: str) -> str:
    if not requester_id:
        return ""
    name = html.escape(requester_name or "کاربر")
    return f'\n🎧 درخواست: <a href="tg://user?id={requester_id}">{name}</a>'


# ════════════════════════════════════════════════════════════
#  ساختِ هاب
# ════════════════════════════════════════════════════════════
def build_panel(state: str, title: str, queue_len: int,
                performer: str = "", duration: int = 0, with_video: bool = False,
                requester_id: int = None, requester_name: str = "",
                loop_mode: str = LOOP_NONE, volume: int = 100):
    safe_title   = html.escape(title or "نامشخص")
    info         = _info_line(performer, duration)
    req_line     = _requester_line(requester_id, requester_name)
    queue_line   = f"\n\n📋 در صف: <b>{queue_len}</b> آهنگ" if queue_len > 0 else ""
    icon         = "🎬" if with_video else "🎧"
    is_muted     = (volume == 0)
    vol_line     = "\n🔇 بی‌صدا" if is_muted else f"\n🔊 صدا: {volume}%"
    mute_label   = "🔇 پخشِ صدا" if is_muted else "🔈 قطع صدا"
    loop_label   = _LOOP_LABELS.get(loop_mode, "🔁 لوپ: خاموش")

    if state == "playing":
        text = f"🎵 <b>در حال پخش</b>\n{icon} {safe_title}{info}{req_line}{vol_line}{queue_line}"
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("⏸ توقف",   callback_data="mus_pause", style="primary"),
            InlineKeyboardButton("⏭ بعدی",   callback_data="mus_skip", style="primary"),
        )
        kb.row(InlineKeyboardButton("⏹️ پایان پخش", callback_data="mus_stop", style="primary"))
        kb.row(
            InlineKeyboardButton("🔀 شافل",        callback_data="mus_shuffle", style="success"),
            InlineKeyboardButton(loop_label,         callback_data="mus_loop", style="success"),
        )
        kb.row(
            InlineKeyboardButton(f"🔉 -{VOLUME_STEP}%", callback_data="mus_vol_down"),
            InlineKeyboardButton(mute_label,             callback_data="mus_mute", style="success" if is_muted else None),
            InlineKeyboardButton(f"🔊 +{VOLUME_STEP}%", callback_data="mus_vol_up"),
        )
        kb.row(
            InlineKeyboardButton("❤️ لایک",          callback_data="mus_like"),
            InlineKeyboardButton("💔 دیسلایک",       callback_data="mus_dislike"),
        )
        kb.row(InlineKeyboardButton("📋 نمایش آهنگ‌های لیست", callback_data="mus_queue", style="success"))
        kb.row(InlineKeyboardButton("❌ بستن هاب",  callback_data="mus_close", style="danger"))
        return text, kb

    if state == "paused":
        text = f"⏸ <b>متوقف شده</b>\n{icon} {safe_title}{info}{req_line}{vol_line}{queue_line}"
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("▶️ ادامه",  callback_data="mus_resume", style="primary"),
            InlineKeyboardButton("⏭ بعدی",   callback_data="mus_skip", style="primary"),
        )
        kb.row(InlineKeyboardButton("⏹️ پایان پخش", callback_data="mus_stop", style="primary"))
        kb.row(
            InlineKeyboardButton("🔀 شافل",        callback_data="mus_shuffle", style="success"),
            InlineKeyboardButton(loop_label,         callback_data="mus_loop", style="success"),
        )
        kb.row(
            InlineKeyboardButton(f"🔉 -{VOLUME_STEP}%", callback_data="mus_vol_down"),
            InlineKeyboardButton(mute_label,             callback_data="mus_mute", style="success" if is_muted else None),
            InlineKeyboardButton(f"🔊 +{VOLUME_STEP}%", callback_data="mus_vol_up"),
        )
        kb.row(
            InlineKeyboardButton("❤️ لایک",          callback_data="mus_like"),
            InlineKeyboardButton("💔 دیسلایک",       callback_data="mus_dislike"),
        )
        kb.row(InlineKeyboardButton("📋 نمایش آهنگ‌های لیست", callback_data="mus_queue", style="success"))
        kb.row(InlineKeyboardButton("❌ بستن هاب",  callback_data="mus_close", style="danger"))
        return text, kb

    text = "✅ <b>پخش به پایان رسید.</b>\nاگر تا چند دقیقه آهنگی پخش نشود، از ویس‌چت خارج می‌شوم."
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🚪 خروج از ویس‌چت", callback_data="mus_kick", style="danger"))
    return text, kb


def build_queue_added(title: str, performer: str, duration: int, position: int) -> str:
    safe_title = html.escape(title or "نامشخص")
    info       = _info_line(performer, duration)
    return (
        f"➕ <b>به صف اضافه شد</b>\n🎧 {safe_title}{info}"
        f"\n\n📋 موقعیت در صف: <b>{position}</b>"
    )


# ════════════════════════════════════════════════════════════
#  مجوز
# ════════════════════════════════════════════════════════════
async def _is_authorized(chat_id: int, user_id: int) -> bool:
    if user_id in SUPER_USERS:
        return True
    data = get_now(chat_id)
    return data.get("initiator_id") == user_id


def register_userbot_handlers(bot: AsyncTeleBot):

    # ── دستور «پخش» ────────────────────────────────────────
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

        if (user_id not in SUPER_USERS) and (chat_id != MUSIC_GROUP_ID):
            await bot.reply_to(message, "⛔ فقط مدیران اجازهٔ پخش موزیک دارند.")
            return

        replied    = message.reply_to_message
        file_id    = None
        file_size  = 0
        performer  = ""
        duration   = 0
        with_video = False
        file_unique_id = ""

        if replied.audio:
            title          = replied.audio.title or replied.audio.file_name or "آهنگ ناشناس"
            performer      = replied.audio.performer or ""
            duration       = replied.audio.duration or 0
            file_id        = replied.audio.file_id
            file_size      = replied.audio.file_size or 0
            file_unique_id = replied.audio.file_unique_id or ""
        elif replied.voice:
            title          = "پیام صوتی"
            duration       = replied.voice.duration or 0
            file_id        = replied.voice.file_id
            file_size      = replied.voice.file_size or 0
            file_unique_id = replied.voice.file_unique_id or ""
        elif replied.video:
            title          = replied.video.file_name or "ویدیو"
            duration       = replied.video.duration or 0
            file_id        = replied.video.file_id
            file_size      = replied.video.file_size or 0
            file_unique_id = replied.video.file_unique_id or ""
            with_video     = True
        elif replied.video_note:
            title          = "پیام ویدیویی"
            duration       = replied.video_note.duration or 0
            file_id        = replied.video_note.file_id
            file_size      = replied.video_note.file_size or 0
            file_unique_id = replied.video_note.file_unique_id or ""
            with_video     = True
        elif replied.animation:
            title          = replied.animation.file_name or "گیف/انیمیشن"
            duration       = replied.animation.duration or 0
            file_id        = replied.animation.file_id
            file_size      = replied.animation.file_size or 0
            file_unique_id = replied.animation.file_unique_id or ""
            with_video     = True
        elif replied.document and (replied.document.mime_type or "").startswith("audio"):
            title          = replied.document.file_name or "فایل صوتی"
            file_id        = replied.document.file_id
            file_size      = replied.document.file_size or 0
            file_unique_id = replied.document.file_unique_id or ""
        elif replied.document and (replied.document.mime_type or "").startswith("video"):
            title          = replied.document.file_name or "ویدیو"
            file_id        = replied.document.file_id
            file_size      = replied.document.file_size or 0
            file_unique_id = replied.document.file_unique_id or ""
            with_video     = True
        else:
            await bot.reply_to(message, "❗️ لطفاً روی یک فایل صوتی یا ویدیویی ریپلای کنید.")
            return

        kind = "ویدیو" if with_video else "موزیک"
        panel = await bot.reply_to(
            message,
            f"🔄 در حال اتصال به ویس‌چت برای پخش {kind} «{html.escape(title)}»...",
            parse_mode="HTML",
        )

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

        requester_name = message.from_user.first_name or ""

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
            file_unique_id=file_unique_id,
            requester_name=requester_name,
        ))

    # ── دستورهای متنیِ کنترل ────────────────────────────────
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

        if not get_now(chat_id):
            await bot.reply_to(message, "🔇 الان چیزی در حال پخش نیست.")
            return

        if not await _is_authorized(chat_id, user_id):
            await bot.reply_to(message, "⛔ فقط کسی که پخش را شروع کرده می‌تواند این کار را انجام دهد.")
            return

        if cmd in ("بعدی", "/skip"):
            asyncio.create_task(cmd_skip(chat_id))
            await bot.reply_to(message, "⏭ رفتم سراغ آهنگِ بعدیِ صف.")
        else:
            asyncio.create_task(cmd_stop(chat_id))
            await bot.reply_to(message, "⛔ پخش متوقف شد و از ویس‌چت خارج می‌شوم.")

    # ── دستور «هاب» ────────────────────────────────────────
    @bot.message_handler(
        func=lambda m: (
            m.chat.type in ("group", "supergroup")
            and m.text is not None
            and m.text.strip() in ("هاب", "/hub")
        ),
        content_types=["text"],
    )
    async def handle_hub_command(message):
        chat_id = message.chat.id
        now = get_now(chat_id)
        if not now:
            await bot.reply_to(message, "🔇 الان چیزی در حال پخش نیست تا هابی نشان دهم.")
            return

        text, kb = build_panel(
            now.get("state", "idle"),
            now.get("title", ""),
            get_queue_len(chat_id),
            now.get("performer", ""),
            now.get("duration", 0),
            now.get("with_video", False),
            now.get("requester_id"),
            now.get("requester_name", ""),
            get_loop(chat_id),
            get_volume(chat_id),
        )
        sent = await bot.reply_to(message, text, parse_mode="HTML", reply_markup=kb)
        repoint_panel(chat_id, sent.message_id)

    # ── دستور «علاقه‌مندی‌ها» ──────────────────────────────
    @bot.message_handler(
        func=lambda m: (
            m.chat.type in ("group", "supergroup")
            and m.text is not None
            and m.text.strip() in ("علاقه‌مندی‌ها", "علاقمندی ها", "/favorites", "/favs")
        ),
        content_types=["text"],
    )
    async def handle_favorites_command(message):
        chat_id = message.chat.id
        user_id = message.from_user.id

        from src.database.db_manager import music_get_favorites
        favs = await music_get_favorites(user_id, chat_id)
        if not favs:
            await bot.reply_to(message, "💔 هنوز هیچ آهنگی رو توی این گروه لایک نکردی.")
            return

        now = get_now(chat_id)
        panel = await bot.reply_to(
            message,
            f"❤️ در حال اضافه کردن <b>{len(favs)}</b> آهنگِ علاقه‌مندی به صف...",
            parse_mode="HTML",
        )

        added = 0
        for fav in favs:
            from src.bot.music_protocol import push_to_queue as _ptq
            _ptq(chat_id, {
                "audio_chat_id":  chat_id,
                "audio_msg_id":   fav["msg_id"],
                "title":          fav["title"] or "آهنگ ناشناس",
                "performer":      fav["performer"] or "",
                "duration":       fav["duration"] or 0,
                "requester_id":   user_id,
                "requester_name": message.from_user.first_name or "",
                "audio_path":     None,
                "with_video":     False,
                "file_unique_id": fav["file_unique_id"],
            })
            added += 1

        await bot.edit_message_text(
            f"❤️ <b>{added}</b> آهنگ از علاقه‌مندی‌هات به صف اضافه شد.",
            chat_id, panel.message_id, parse_mode="HTML"
        )

        if not now:
            # اگر هیچ چیزی پخش نمی‌شود، اولی را شروع کنیم
            from src.bot.music_protocol import pop_from_queue as _pfq
            first = _pfq(chat_id)
            if first:
                asyncio.create_task(cmd_play(
                    chat_id=chat_id,
                    audio_chat_id=first["audio_chat_id"],
                    audio_msg_id=first["audio_msg_id"],
                    title=first["title"],
                    requester_id=user_id,
                    initiator_id=user_id,
                    panel_msg_id=panel.message_id,
                    audio_path=first.get("audio_path"),
                    performer=first["performer"],
                    duration=first["duration"],
                    file_unique_id=first.get("file_unique_id", ""),
                    requester_name=first.get("requester_name", ""),
                ))

    # ── دستور «تاریخچه» ────────────────────────────────────
    @bot.message_handler(
        func=lambda m: (
            m.chat.type in ("group", "supergroup")
            and m.text is not None
            and m.text.strip() in ("تاریخچه", "/history")
        ),
        content_types=["text"],
    )
    async def handle_history_command(message):
        chat_id = message.chat.id
        history = get_history(chat_id)
        if not history:
            await bot.reply_to(message, "📜 هنوز آهنگی پخش نشده.")
            return

        lines = []
        for i, t in enumerate(history[:10], start=1):
            t_title = html.escape((t.get("title") or "نامشخص")[:35])
            dur     = _fmt_duration(t.get("duration", 0))
            line    = f"{i}. {t_title}"
            if dur:
                line += f" ({dur})"
            lines.append(line)

        await bot.reply_to(
            message,
            f"📜 <b>تاریخچهٔ پخش (آخرین {len(lines)}):</b>\n" + "\n".join(lines),
            parse_mode="HTML"
        )

    # ── کال‌بکِ دکمه‌های هاب ───────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("mus_"))
    async def handle_music_buttons(call):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        data    = call.data[4:]  # strip "mus_"

        # ── دکمه‌های بدونِ نیاز به مجوز ──────────────────
        if data == "queue":
            tracks = peek_queue(chat_id)
            if not tracks:
                await bot.answer_callback_query(call.id, "📋 صف خالیه.", show_alert=True)
                return
            lines = []
            for i, t in enumerate(tracks[:15], start=1):
                t_title = (t.get("title") or "نامشخص")[:28]
                dur     = _fmt_duration(t.get("duration", 0))
                line    = f"{i}. {t_title}"
                if dur:
                    line += f" ({dur})"
                lines.append(line)
            text = "📋 آهنگ‌های صف:\n" + "\n".join(lines)
            if len(tracks) > 15:
                text += f"\n…و {len(tracks) - 15} مورد دیگر"
            if len(text) > 195:
                text = text[:195] + "…"
            await bot.answer_callback_query(call.id, text, show_alert=True)
            return

        if data == "queue_ok":
            try:
                base_text = call.message.html_text or ""
            except Exception:
                base_text = ""
            new_text = f"{base_text}\n\n☑️ <i>ترتیبِ صف حفظ شد.</i>"
            try:
                await bot.edit_message_text(
                    new_text, call.message.chat.id, call.message.message_id,
                    parse_mode="HTML", reply_markup=None
                )
            except Exception:
                pass
            await bot.answer_callback_query(call.id, "✅ ترتیب حفظ شد.")
            return

        # ── پخش بعدی این باشه ─────────────────────────────
        if data.startswith("playnext_"):
            if not await _is_authorized(chat_id, user_id):
                await bot.answer_callback_query(call.id, "⛔ فقط آغازگر یا ادمین!", show_alert=True)
                return
            try:
                idx = int(data.split("playnext_")[-1])
                asyncio.create_task(cmd_move_to_front(chat_id, idx))
                # پیامِ «به صف اضافه شد» را ویرایش می‌کنیم: دکمه‌ها حذف می‌شوند و
                # متن نشان می‌دهد که ربات تصمیمِ کاربر را متوجه شده.
                try:
                    base_text = call.message.html_text or ""
                except Exception:
                    base_text = ""
                new_text = f"{base_text}\n\n▶️ <i>این آهنگ بعدی پخش می‌شه!</i>"
                try:
                    await bot.edit_message_text(
                        new_text, call.message.chat.id, call.message.message_id,
                        parse_mode="HTML", reply_markup=None
                    )
                except Exception:
                    pass
                await bot.answer_callback_query(call.id, "▶️ این آهنگ بعدی پخش می‌شه!")
            except Exception as e:
                await bot.answer_callback_query(call.id, f"خطا: {e}", show_alert=True)
            return

        # ── خروج از ویس‌چت (وقتی هاب idle است) ──────────────
        if data == "kick":
            if not await _is_authorized(chat_id, user_id):
                await bot.answer_callback_query(call.id, "⛔ فقط آغازگر یا ادمین!", show_alert=True)
                return
            asyncio.create_task(cmd_stop(chat_id))
            try:
                await bot.delete_message(chat_id, call.message.message_id)
            except Exception:
                pass
            await bot.answer_callback_query(call.id, "🚪 یوزربات از ویس‌چت خارج شد.")
            return

        # ── بستن هاب ──────────────────────────────────────
        if data == "close":
            if not await _is_authorized(chat_id, user_id):
                await bot.answer_callback_query(call.id, "⛔ فقط آغازگر یا ادمین!", show_alert=True)
                return
            try:
                await bot.delete_message(chat_id, call.message.message_id)
            except Exception as e:
                await bot.answer_callback_query(call.id, "⚠️ حذف ممکن نشد.", show_alert=True)
            return

        # ── لایک / دیسلایک ────────────────────────────────
        if data in ("like", "dislike"):
            now = get_now(chat_id)
            if not now:
                await bot.answer_callback_query(call.id, "چیزی پخش نمی‌شود.", show_alert=True)
                return
            fuid = now.get("file_unique_id", "")
            if not fuid:
                await bot.answer_callback_query(call.id, "⚠️ این فایل قابل ذخیره نیست.", show_alert=True)
                return

            from src.database.db_manager import music_like, music_dislike
            if data == "like":
                await music_like(
                    user_id, chat_id,
                    now.get("audio_msg_id", 0),
                    fuid,
                    now.get("title", ""),
                    now.get("performer", ""),
                    now.get("duration", 0),
                )
                await bot.answer_callback_query(call.id, "❤️ به علاقه‌مندی‌هات اضافه شد!")
            else:
                await music_dislike(user_id, chat_id, fuid)
                asyncio.create_task(cmd_skip(chat_id))
                await bot.answer_callback_query(call.id, "💔 رد شد و دیگر برات پخش نمی‌شه.")
            return

        # ── دکمه‌های نیازمند مجوز ─────────────────────────
        if not await _is_authorized(chat_id, user_id):
            await bot.answer_callback_query(call.id, "⛔ این هاب برای شما نیست!", show_alert=True)
            return

        labels = {
            "pause":    "⏸ توقف شد",
            "resume":   "▶️ ادامه یافت",
            "skip":     "⏭ آهنگ بعدی",
            "stop":     "⏹️ پخش پایان یافت",
            "shuffle":  "🔀 صف قاطی شد!",
        }

        if data == "pause":
            asyncio.create_task(cmd_pause(chat_id))
        elif data == "resume":
            asyncio.create_task(cmd_resume(chat_id))
        elif data == "skip":
            asyncio.create_task(cmd_skip(chat_id))
        elif data == "stop":
            asyncio.create_task(cmd_stop(chat_id))
        elif data == "shuffle":
            asyncio.create_task(cmd_shuffle(chat_id))
        elif data == "loop":
            new_mode = await cmd_loop(chat_id)
            loop_names = {LOOP_NONE: "خاموش", LOOP_TRACK: "یک آهنگ", LOOP_QUEUE: "همهٔ صف"}
            await bot.answer_callback_query(call.id, f"🔁 لوپ: {loop_names.get(new_mode, new_mode)}")
            return
        elif data in ("vol_up", "vol_down"):
            # مستقیم await می‌شود (نه fire-and-forget) تا مقدارِ واقعیِ ولوم بعد از
            # تغییر معلوم باشه و تو toast نشون داده بشه — نه یه پیامِ ژنریک.
            try:
                new_vol = await cmd_volume(chat_id, VOLUME_STEP if data == "vol_up" else -VOLUME_STEP)
                await bot.answer_callback_query(call.id, f"🔊 {new_vol}%")
            except Exception as e:
                print(f"💥 vol_up/down error: {e}")
                await bot.answer_callback_query(call.id, "⚠️ تغییر صدا انجام نشد.")
            return
        elif data == "mute":
            try:
                new_vol = await cmd_mute(chat_id)
                await bot.answer_callback_query(
                    call.id, "🔇 صدا قطع شد." if new_vol == 0 else f"🔊 صدا وصل شد ({new_vol}%)."
                )
            except Exception as e:
                print(f"💥 mute error: {e}")
                await bot.answer_callback_query(call.id, "⚠️ تغییر صدا انجام نشد.")
            return
        else:
            await bot.answer_callback_query(call.id)
            return

        await bot.answer_callback_query(call.id, labels.get(data, "✅ انجام شد"))

    print("🎵 Userbot music bridge handlers registered.")


async def start_music_event_listener(bot: AsyncTeleBot):
    """[DEPRECATED] — باقی مانده جهت جلوگیری از ImportError در main.py."""
    print("🌙 Music event listener (In-Memory Mode) initialized natively.")
    while True:
        await asyncio.sleep(3600)