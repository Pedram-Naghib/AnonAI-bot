"""
یوزربات موزیک یکپارچه (In-Memory Mode) — سازگار با py-tgcalls==2.3.3 و Telethon.

نکته‌ی مهم درباره‌ی این بازنویسی:
  نسخه‌ی قبلی این فایل با API قدیمی py-tgcalls (نسخه‌ی 0.9.x) نوشته شده بود
  (AudioPiped / join_group_call / on_stream_end). این متدها در نسخه‌ی 2.3.3
  که در requirements.txt نصب می‌شود اصلاً وجود ندارند، بنابراین خودِ import
  بالای فایل با ModuleNotFoundError می‌شکست و کل ربات هنگام بالا آمدن کرش می‌کرد.

  حالا از API صحیح نسخه‌ی 2.x استفاده می‌کنیم:
    • from pytgcalls.types import MediaStream, StreamEnded
    • await calls.play(chat_id, MediaStream(...))
    • await calls.pause(chat_id) / await calls.resume(chat_id)
    • await calls.leave_call(chat_id)
    • @calls.on_update()  → تشخیص پایان آهنگ با isinstance(update, StreamEnded)
"""

import os
import asyncio

from telethon import TelegramClient
from telethon.sessions import StringSession

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, StreamEnded
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError

from telebot.async_telebot import AsyncTeleBot

# تضمین در دسترس بودن ffmpeg (py-tgcalls برای پخش فایل به ffmpeg نیاز دارد)
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()  # ffmpeg/ffprobe را روی PATH اضافه می‌کند
except Exception as _e:
    print(f"⚠️ static_ffmpeg setup skipped: {_e}")

from src.bot.music_protocol import (
    get_now, set_now, clear_now, get_queue_len,
    push_to_queue, pop_from_queue, clear_queue, IDLE_TIMEOUT
)

# ── پیکربندی ──────────────────────────────────────────────
API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
DOWNLOAD_DIR = "downloads"

# روی Render فایل‌سیستم موقتی است و کامیت کردن فایل سشن خطرناک است؛
# اگر USERBOT_SESSION در محیط ست شده باشد از StringSession استفاده می‌کنیم،
# در غیر این صورت روی VPS از فایل userbot.session استفاده می‌شود.
_STRING_SESSION = os.getenv("USERBOT_SESSION", "").strip()
if _STRING_SESSION:
    print("🔑 Using StringSession from env (USERBOT_SESSION).")
    client = TelegramClient(StringSession(_STRING_SESSION), API_ID, API_HASH)
else:
    print("🔑 Using file session: userbot.session")
    client = TelegramClient("userbot", API_ID, API_HASH)

calls = PyTgCalls(client)

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
    # برای دانلود، یوزربات باید عضو گروه باشد وگرنه get_messages چیزی برنمی‌گرداند.
    msg = await client.get_messages(chat_id, ids=msg_id)
    if not msg:
        return ""
    path = await client.download_media(msg, file=os.path.join(DOWNLOAD_DIR, f"{chat_id}_{msg_id}"))
    return path or ""


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
#  منطقِ پخش / صف (py-tgcalls 2.3.3)
# ════════════════════════════════════════════════════════════
async def _start_stream(chat_id: int, track: dict) -> str:
    path = await _download_audio(track["audio_chat_id"], track["audio_msg_id"])
    if not path:
        raise ValueError("DOWNLOAD_FAILED")

    try:
        # فقط صدا؛ ویدئو نادیده گرفته شود. play خودش وارد ویس‌چت می‌شود.
        await calls.play(
            chat_id,
            MediaStream(path, video_flags=MediaStream.Flags.IGNORE),
        )
    except Exception:
        _cleanup_file(path)
        raise
    return path


async def cmd_play(chat_id: int, audio_chat_id: int, audio_msg_id: int, title: str,
                   requester_id: int, initiator_id: int, panel_msg_id: int):
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
    except NoActiveGroupCall:
        await _emit_toast(chat_id, "⚠️ ابتدا یک ویس‌چت در گروه ایجاد کنید، سپس دوباره «پخش» را بزنید.")
        return
    except ValueError as e:
        if str(e) == "DOWNLOAD_FAILED":
            await _emit_toast(chat_id, "⚠️ فایل صوتی دانلود نشد. مطمئن شوید یوزربات در این گروه عضو است.")
        else:
            await _emit_toast(chat_id, "⚠️ خطا در آماده‌سازی پخش.")
        print(f"💥 play error in {chat_id}: {e}")
        return
    except Exception as e:
        await _emit_toast(chat_id, "⚠️ اتصال به ویس‌چت ناموفق بود. یوزربات عضو گروه است و ویس‌چت باز است؟")
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
    except NotInCallError:
        pass
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
#  پایانِ طبیعیِ استریم (py-tgcalls 2.3.3)
# ════════════════════════════════════════════════════════════
@calls.on_update()
async def _on_update(_, update):
    # فقط پایانِ آهنگ صوتی برایمان مهم است.
    if isinstance(update, StreamEnded) and update.stream_type == StreamEnded.Type.AUDIO:
        await _play_next(update.chat_id)


# ════════════════════════════════════════════════════════════
#  راه‌اندازی
# ════════════════════════════════════════════════════════════
async def start_music_client(bot_instance: AsyncTeleBot):
    global _bot_instance
    _bot_instance = bot_instance

    if not API_ID or not API_HASH:
        print("⚠️ API_ID/API_HASH تنظیم نشده‌اند — موتور موزیک غیرفعال ماند.")
        return

    _sweep_stale_downloads()
    try:
        await client.start()
        await calls.start()
        me = await client.get_me()
        print(f"✅ Userbot + PyTgCalls started (2.3.3). Logged in as: {getattr(me, 'username', None) or me.id}")
    except Exception as e:
        print(f"💥 Music client failed to start: {e}")