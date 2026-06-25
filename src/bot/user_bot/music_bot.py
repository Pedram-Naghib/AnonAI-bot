"""
یوزربات موزیک یکپارچه (Single-Process) — Telethon + PyTgCalls

در این معماری جدید، Redis کاملاً حذف شده است. یوزربات و ربات رسمی هر دو در یک
Event Loop اجرا می‌شوند. این فایل دیگر به صورت مستقل اجرا نمی‌شود، بلکه تابع 
استارتاپ آن توسط فایل main.py فراخوانی می‌گردد.
"""

import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, StreamEnded
from telebot.async_telebot import AsyncTeleBot

# 🌟 وارد کردن توابع حافظه موقت (بدون نیاز به await)
from src.bot.music_protocol import (
    get_now, set_now, clear_now, get_queue_len, 
    push_to_queue, pop_from_queue, clear_queue, IDLE_TIMEOUT
)

# ── پیکربندی ──────────────────────────────────────────────
API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
DOWNLOAD_DIR = "downloads"

_session_string = os.getenv("USERBOT_SESSION", "").strip()
SESSION_NAME     = os.getenv("SESSION_NAME", "userbot")

if _session_string:
    session = StringSession(_session_string)
    print("🔑 Using StringSession from USERBOT_SESSION env var.")
else:
    session = SESSION_NAME
    print(f"🔑 Using file session: {SESSION_NAME}.session")

# ── کلاینت‌ها ─────────────────────────────────────────────
client  = TelegramClient(session, API_ID, API_HASH)
calls    = PyTgCalls(client)

_autoleave_tasks: dict = {}
_last_panel: dict = {}

# 🌟 متغیری برای نگه‌داشتن کلاینت ربات رسمی (Telebot) جهت ویرایش دکمه‌ها
_bot_instance = None 

# ════════════════════════════════════════════════════════════
#  ارسالِ رویداد به ربات رسمی (مستقیم)
# ════════════════════════════════════════════════════════════
async def _emit_panel(chat_id: int):
    """ویرایش مستقیم پنل دکمه‌ها در گروه بدون نیاز به واسطه."""
    if not _bot_instance:
        return
        
    # ایمپورت محلی برای جلوگیری از مشکل Circular Import (لوپ بین دو فایل)
    from src.bot.handlers.userbot_cmds import build_panel 
    
    now = get_now(chat_id)
    if not now:
        text, kb = build_panel("idle", "", 0)
        panel_msg_id = _last_panel.get(chat_id)
        if panel_msg_id:
            try:
                await _bot_instance.edit_message_text(
                    text, chat_id, panel_msg_id, parse_mode="HTML", reply_markup=kb
                )
            except Exception:
                pass
        return

    text, kb = build_panel(
        now.get("state", "idle"),
        now.get("title", ""),
        get_queue_len(chat_id)
    )
    try:
        await _bot_instance.edit_message_text(
            text, chat_id, now.get("panel_msg_id"),
            parse_mode="HTML", reply_markup=kb
        )
    except Exception:
        pass


async def _emit_toast(chat_id: int, text: str):
    """ارسال مستقیم یک پیام کوتاه در گروه."""
    if not _bot_instance:
        return
    try:
        await _bot_instance.send_message(chat_id, text, parse_mode="HTML")
    except Exception:
        pass


# ════════════════════════════════════════════════════════════
#  دانلودِ صوت
# ════════════════════════════════════════════════════════════
async def _download_audio(chat_id: int, msg_id: int) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    msg = await client.get_messages(chat_id, ids=msg_id)
    path = await client.download_media(msg, file=os.path.join(DOWNLOAD_DIR, f"{chat_id}_{msg_id}"))
    return path


def _cleanup_file(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _sweep_stale_downloads():
    if not os.path.isdir(DOWNLOAD_DIR):
        return
    for fname in os.listdir(DOWNLOAD_DIR):
        try:
            os.remove(os.path.join(DOWNLOAD_DIR, fname))
        except Exception:
            pass


# ════════════════════════════════════════════════════════════
#  منطقِ پخش / صف
# ════════════════════════════════════════════════════════════
async def _start_stream(chat_id: int, track: dict):
    path = await _download_audio(track["audio_chat_id"], track["audio_msg_id"])
    try:
        await calls.play(chat_id, MediaStream(path))
    except Exception:
        _cleanup_file(path)
        raise
    return path


async def cmd_play(chat_id: int, audio_chat_id: int, audio_msg_id: int, title: str, requester_id: int, initiator_id: int, panel_msg_id: int):
    """صدا زده شده به صورت مستقیم توسط هندلر دستور پخش ربات رسمی."""
    track = {
        "audio_chat_id": audio_chat_id,
        "audio_msg_id":  audio_msg_id,
        "title":         title,
        "requester_id":  requester_id,
    }
    _last_panel[chat_id] = panel_msg_id
    now = get_now(chat_id)

    # اگر چیزی در حال پخش/مکث است → به صف اضافه کن
    if now and now.get("state") in ("playing", "paused"):
        pos = push_to_queue(chat_id, track)
        await _emit_toast(chat_id, f"🎵 «{track['title']}» به صف اضافه شد (موقعیت {pos}).")
        await _emit_panel(chat_id)
        return

    # وگرنه همین حالا پخش کن
    try:
        path = await _start_stream(chat_id, track)
    except Exception as e:
        await _emit_toast(chat_id, "⚠️ ابتدا یک ویس‌چت در گروه ایجاد کنید، سپس دوباره «پخش» را بزنید.")
        print(f"💥 play error in {chat_id}: {e}")
        return

    set_now(chat_id, {
        **track,
        "state":        "playing",
        "panel_msg_id": panel_msg_id,
        "initiator_id": initiator_id,
        "path":         path,
    })
    _cancel_autoleave(chat_id)
    await _emit_panel(chat_id)


async def _play_next(chat_id: int):
    prev = get_now(chat_id)
    if prev:
        _cleanup_file(prev.get("path"))

    track = pop_from_queue(chat_id)
    if track:  # اگر صفی وجود داشت
        try:
            path = await _start_stream(chat_id, track)
        except Exception as e:
            print(f"💥 next-play error in {chat_id}: {e}")
            await _play_next(chat_id)
            return
        set_now(chat_id, {
            **track,
            "state":        "playing",
            "panel_msg_id": prev.get("panel_msg_id") if prev else _last_panel.get(chat_id),
            "initiator_id": prev.get("initiator_id") if prev else None,
            "path":         path,
        })
        _cancel_autoleave(chat_id)
        await _emit_panel(chat_id)
    else:  # اگر صف خالی بود
        clear_now(chat_id)
        await _emit_panel(chat_id)
        _schedule_autoleave(chat_id)


async def cmd_pause(chat_id: int):
    try:
        await calls.pause(chat_id)
    except Exception:
        pass
    now = get_now(chat_id)
    if now:
        now["state"] = "paused"
        set_now(chat_id, now)
    await _emit_panel(chat_id)


async def cmd_resume(chat_id: int):
    try:
        await calls.resume(chat_id)
    except Exception:
        pass
    now = get_now(chat_id)
    if now:
        now["state"] = "playing"
        set_now(chat_id, now)
    await _emit_panel(chat_id)


async def cmd_skip(chat_id: int):
    if get_queue_len(chat_id) > 0:
        await _play_next(chat_id)
    else:
        await _leave(chat_id, "⏭ آهنگ بعدی‌ای در صف نبود؛ از ویس‌چت خارج شدم.")


async def cmd_stop(chat_id: int):
    clear_queue(chat_id)
    await _leave(chat_id, "⛔ پخش پایان یافت و از ویس‌چت خارج شدم.")


async def _leave(chat_id: int, toast: str = ""):
    now = get_now(chat_id)
    if now:
        _cleanup_file(now.get("path"))
    try:
        await calls.leave_call(chat_id)
    except Exception:
        pass
    clear_now(chat_id)
    _cancel_autoleave(chat_id)
    await _emit_panel(chat_id)
    if toast:
        await _emit_toast(chat_id, toast)


# ════════════════════════════════════════════════════════════
#  خروج خودکار
# ════════════════════════════════════════════════════════════
def _schedule_autoleave(chat_id: int):
    _cancel_autoleave(chat_id)

    async def _waiter():
        try:
            await asyncio.sleep(IDLE_TIMEOUT)
            if not get_now(chat_id):
                await _leave(chat_id, "🌙 به‌خاطر بیکاری، از ویس‌چت خارج شدم.")
        except asyncio.CancelledError:
            pass

    _autoleave_tasks[chat_id] = asyncio.create_task(_waiter())


def _cancel_autoleave(chat_id: int):
    task = _autoleave_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


# ════════════════════════════════════════════════════════════
#  پایانِ طبیعیِ استریم
# ════════════════════════════════════════════════════════════
@calls.on_update()
async def _on_update(_, update):
    if isinstance(update, StreamEnded):
        await _play_next(update.chat_id)


# ════════════════════════════════════════════════════════════
#  راه‌اندازی (صدا زده می‌شود از main.py)
# ════════════════════════════════════════════════════════════
async def start_music_client(bot_instance: AsyncTeleBot):
    """
    روشن کردن کلاینت تلتون و ویس‌چت و ثبت ریفرنس ربات رسمی
    """
    global _bot_instance
    _bot_instance = bot_instance
    
    _sweep_stale_downloads()
    await client.start()
    await calls.start()
    print("✅ Userbot + PyTgCalls started (Single-Process In-Memory Mode).")