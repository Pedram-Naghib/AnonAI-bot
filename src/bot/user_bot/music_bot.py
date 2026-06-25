"""
یوزربات موزیک یکپارچه (In-Memory Mode) — مخصوص py-tgcalls==2.3.3 و فایل سشن.

تغییرات:
  ۱. حذف کامل وابستگی به USERBOT_SESSION استرینگ و اجبار به استفاده از فایل userbot.session
  ۲. بازگرداندن متدهای پخش به AudioPiped و join_group_call مخصوص نسخه 2.3.3
"""

import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# 🌟 ایمپورت متدهای بومی نسخه 2.3.3
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import AudioPiped

from telebot.async_telebot import AsyncTeleBot

# وارد کردن توابع حافظه موقت (بدون نیاز به await)
from src.bot.music_protocol import (
    get_now, set_now, clear_now, get_queue_len, 
    push_to_queue, pop_from_queue, clear_queue, IDLE_TIMEOUT
)

# ── پیکربندی ──────────────────────────────────────────────
API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
DOWNLOAD_DIR = "downloads"

# 🌟 اجبارِ برنامه به استفاده از فایلِ سشنِ فیزیکی کنار پروژه به جای استرینگ
SESSION_NAME = "userbot" 
print(f"🔑 Strict Mode: Using file session directly from {SESSION_NAME}.session")

# ── کلاینت‌ها ─────────────────────────────────────────────
client  = TelegramClient(SESSION_NAME, API_ID, API_HASH)
calls    = PyTgCalls(client)

_autoleave_tasks: dict = {}
_last_panel: dict = {}
_bot_instance = None 

# ════════════════════════════════════════════════════════════
#  ارسالِ رویداد به ربات رسمی (مستقیم)
# ════════════════════════════════════════════════════════════
async def _emit_panel(chat_id: int):
    if not _bot_instance:
        return
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
    if not msg:
        return ""
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
#  منطقِ پخش / صف (v2.3.3)
# ════════════════════════════════════════════════════════════
async def _start_stream(chat_id: int, track: dict):
    path = await _download_audio(track["audio_chat_id"], track["audio_msg_id"])
    if not path:
        raise ValueError("فایل صوتی دانلود نشد. مطمئن شوید یوزربات در گروه عضو است.")
        
    try:
        # 🌟 استفاده از متد معتبر نسخه 2.3.3
        await calls.join_group_call(chat_id, AudioPiped(path))
    except Exception:
        _cleanup_file(path)
        raise
    return path


async def cmd_play(chat_id: int, audio_chat_id: int, audio_msg_id: int, title: str, requester_id: int, initiator_id: int, panel_msg_id: int):
    track = {
        "audio_chat_id": audio_chat_id,
        "audio_msg_id":  audio_msg_id,
        "title":         title,
        "requester_id":  requester_id,
    }
    _last_panel[chat_id] = panel_msg_id
    now = get_now(chat_id)

    if now and now.get("state") in ("playing", "paused"):
        pos = push_to_queue(chat_id, track)
        await _emit_toast(chat_id, f"🎵 «{track['title']}» به صف اضافه شد (موقعیت {pos}).")
        await _emit_panel(chat_id)
        return

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
    if track:
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
    else:
        clear_now(chat_id)
        await _emit_panel(chat_id)
        _schedule_autoleave(chat_id)


async def cmd_pause(chat_id: int):
    try:
        # 🌟 متد مکث در نسخه ۲
        await calls.pause_stream(chat_id)
    except Exception:
        pass
    now = get_now(chat_id)
    if now:
        now["state"] = "paused"
        set_now(chat_id, now)
    await _emit_panel(chat_id)


async def cmd_resume(chat_id: int):
    try:
        # 🌟 متد ادامه در نسخه ۲
        await calls.resume_stream(chat_id)
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
        # 🌟 متد لفت در نسخه ۲
        await calls.leave_group_call(chat_id)
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
#  پایانِ طبیعیِ استریم (v2.3.3)
# ════════════════════════════════════════════════════════════
@calls.on_stream_end()
async def _on_stream_end(chat_id: int, _):
    # 🌟 ایونت پایان آهنگ در نسخه ۲.۳.۳
    await _play_next(chat_id)


# ════════════════════════════════════════════════════════════
#  راه‌اندازی
# ════════════════════════════════════════════════════════════
async def start_music_client(bot_instance: AsyncTeleBot):
    global _bot_instance
    _bot_instance = bot_instance
    
    _sweep_stale_downloads()
    await client.start()
    await calls.start()
    print("✅ Userbot + PyTgCalls started (Single-Process Native v2.3.3 File Session).")