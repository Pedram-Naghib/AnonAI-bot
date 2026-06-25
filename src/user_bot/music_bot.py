"""
یوزربات موزیک (پروسهٔ جداگانه) — Telethon + PyTgCalls.

این برنامه با حسابِ کاربری (نه بات) وارد ویس‌چت گروه می‌شود و موزیک پخش می‌کند.
دستورها را از Redis می‌گیرد و وضعیت را به Redis برمی‌گرداند تا «ربات رسمی»
پنل و دکمه‌ها را به‌روزرسانی کند.

اجرا (روی یک سرور always-on، نه Render رایگان):
    pip install -r requirements-userbot.txt
    # ffmpeg باید روی سیستم نصب باشد
    python music_bot.py

متغیرهای محیطی لازم:
    API_ID, API_HASH         → از my.telegram.org
    REDIS_URL                → همان Redis که ربات رسمی استفاده می‌کند

سشن (یکی از این دو راه):
    ۱) USERBOT_SESSION → یک StringSession (برای Render/هاستِ بدونِ دیسکِ دائمی).
       رشته را با اسکریپتِ session_to_string.py از فایلِ سشنِ قبلی‌ات بساز.
    ۲) فایلِ <SESSION_NAME>.session کنارِ این اسکریپت (برای VPS با دیسکِ دائمی).
       اگر USERBOT_SESSION ست نشده باشد، از این فایل استفاده می‌شود.

⚠️ هشدارِ امنیتی: StringSession و فایلِ .session هر دو معادلِ دسترسیِ کاملِ
اکانت‌اند؛ StringSession را فقط در Secret/Environment هاست بگذار، نه در کد یا
گیت. فایلِ .session هم در .gitignore است و هرگز نباید کامیت شود. ترجیحاً از
یک اکانتِ دوم (نه اکانتِ شخصیِ اصلی‌ات) برای این یوزربات استفاده کن.
"""

import os
import json
import asyncio

import redis.asyncio as aioredis
from telethon import TelegramClient
from telethon.sessions import StringSession

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, StreamEnded

from src.bot.music_protocol import (
    CMD_CHANNEL, EVT_CHANNEL, now_key, queue_key, pack, unpack, IDLE_TIMEOUT,
)

# ── پیکربندی ──────────────────────────────────────────────
API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
DOWNLOAD_DIR = "downloads"

# سشن از دو راه ممکن است بیاید:
#   ۱) متغیرِ محیطیِ USERBOT_SESSION (یک StringSession) → برای هاست‌هایی مثلِ
#      Render که دیسکشان دائمی نیست؛ بعد از هر دیپلوی دوباره لاگین لازم نمی‌شود.
#   ۲) فایلِ <SESSION_NAME>.session کنارِ این اسکریپت → برای سرورهای always-on
#      مثلِ یک VPS که دیسک ثابت دارند (روشِ قبلیِ خودِ پروژه).
# اگر متغیرِ محیطی ست شده باشد، همیشه اولویت دارد.
_session_string = os.getenv("USERBOT_SESSION", "").strip()
SESSION_NAME     = os.getenv("SESSION_NAME", "userbot")

if _session_string:
    session = StringSession(_session_string)
    print("🔑 Using StringSession from USERBOT_SESSION env var.")
else:
    session = SESSION_NAME  # تلتون خودش <SESSION_NAME>.session را می‌سازد/می‌خواند
    print(f"🔑 Using file session: {SESSION_NAME}.session")

# ── کلاینت‌ها ─────────────────────────────────────────────
r       = aioredis.from_url(REDIS_URL, decode_responses=True)
client  = TelegramClient(session, API_ID, API_HASH)
calls   = PyTgCalls(client)

# تسک‌های خروج خودکار به ازای هر چت (chat_id → asyncio.Task)
_autoleave_tasks: dict = {}


# ════════════════════════════════════════════════════════════
#  هِلپرهای وضعیت (روی Redis)
# ════════════════════════════════════════════════════════════
async def _get_now(chat_id: int) -> dict:
    raw = await r.get(now_key(chat_id))
    return unpack(raw) if raw else {}


async def _set_now(chat_id: int, data: dict):
    await r.set(now_key(chat_id), pack(data))


async def _clear_now(chat_id: int):
    await r.delete(now_key(chat_id))


async def _queue_len(chat_id: int) -> int:
    return await r.llen(queue_key(chat_id))


# ════════════════════════════════════════════════════════════
#  ارسالِ رویداد به ربات رسمی
# ════════════════════════════════════════════════════════════
async def _emit_panel(chat_id: int):
    """وضعیتِ فعلی را برای رندرِ پنل به ربات رسمی می‌فرستد."""
    now = await _get_now(chat_id)
    if not now:
        # چیزی در حال پخش نیست → پنلِ پایان
        await r.publish(EVT_CHANNEL, pack({
            "event": "panel", "chat_id": chat_id,
            "panel_msg_id": _last_panel.get(chat_id),
            "state": "idle", "title": "", "queue_len": 0,
        }))
        return
    await r.publish(EVT_CHANNEL, pack({
        "event":        "panel",
        "chat_id":      chat_id,
        "panel_msg_id": now.get("panel_msg_id"),
        "state":        now.get("state", "idle"),
        "title":        now.get("title", ""),
        "queue_len":    await _queue_len(chat_id),
    }))


async def _emit_toast(chat_id: int, text: str):
    await r.publish(EVT_CHANNEL, pack({"event": "toast", "chat_id": chat_id, "text": text}))


# آخرین آیدیِ پنل برای هر چت (برای پیامِ پایان وقتی now پاک شده)
_last_panel: dict = {}


# ════════════════════════════════════════════════════════════
#  دانلودِ صوت با آیدیِ پیام (مدیریت حافظه)
# ════════════════════════════════════════════════════════════
async def _download_audio(chat_id: int, msg_id: int) -> str:
    """فایل را فقط هنگام نیاز از روی آیدیِ پیام دانلود می‌کند و مسیرش را می‌دهد."""
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
    """در شروعِ پروسه، هر فایلِ باقی‌مانده از یک کرش/ری‌استارتِ قبلی را پاک می‌کند.
    این تنها فایلِ به‌جا مانده روی دیسک است، پس روی Redis (وضعیتِ «در حال پخش»)
    اثری ندارد — صرفاً جلوگیری از پر شدنِ دیسک در طولِ زمان."""
    if not os.path.isdir(DOWNLOAD_DIR):
        return
    count = 0
    for fname in os.listdir(DOWNLOAD_DIR):
        try:
            os.remove(os.path.join(DOWNLOAD_DIR, fname))
            count += 1
        except Exception:
            pass
    if count:
        print(f"🧹 Swept {count} stale file(s) from {DOWNLOAD_DIR}/ on startup.")


# ════════════════════════════════════════════════════════════
#  منطقِ پخش / صف
# ════════════════════════════════════════════════════════════
async def _start_stream(chat_id: int, track: dict):
    """پیوستن به ویس‌چت و پخشِ یک ترک. مسیر فایل را برای پاک‌سازی برمی‌گرداند.

    اگر پخش (calls.play) با خطا مواجه شود، فایلِ تازه‌دانلودشده همین‌جا حذف
    می‌شود — وگرنه با هر بار «ویس‌چت فعال نیست» یک فایلِ یتیم در دیسک می‌ماند
    که در یک هاستِ کم‌فضا (مثلِ Render) به‌مرور جا را پر می‌کند.
    """
    path = await _download_audio(track["audio_chat_id"], track["audio_msg_id"])
    try:
        # video_flags=IGNORE یعنی فقط صوت پخش شود (در نسخهٔ نصب‌شده اگر فرق داشت، همین‌جا تنظیم کنید)
        await calls.play(chat_id, MediaStream(path, video_flags=MediaStream.Flags.IGNORE))
    except Exception:
        _cleanup_file(path)
        raise
    return path


async def _cmd_play(data: dict):
    chat_id = data["chat_id"]
    track = {
        "audio_chat_id": data["audio_chat_id"],
        "audio_msg_id":  data["audio_msg_id"],
        "title":         data["title"],
        "requester_id":  data["requester_id"],
    }
    _last_panel[chat_id] = data.get("panel_msg_id")
    now = await _get_now(chat_id)

    # اگر چیزی در حال پخش/مکث است → به صف اضافه کن
    if now and now.get("state") in ("playing", "paused"):
        await r.rpush(queue_key(chat_id), pack(track))
        pos = await _queue_len(chat_id)
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

    await _set_now(chat_id, {
        **track,
        "state":        "playing",
        "panel_msg_id": data.get("panel_msg_id"),
        "initiator_id": data.get("initiator_id"),
        "path":         path,
    })
    _cancel_autoleave(chat_id)
    await _emit_panel(chat_id)


async def _play_next(chat_id: int):
    """با پایانِ یک ترک صدا زده می‌شود: ترکِ بعدی یا حالتِ بیکار + خروج خودکار."""
    prev = await _get_now(chat_id)
    if prev:
        _cleanup_file(prev.get("path"))

    raw = await r.lpop(queue_key(chat_id))
    if raw:
        track = unpack(raw)
        try:
            path = await _start_stream(chat_id, track)
        except Exception as e:
            print(f"💥 next-play error in {chat_id}: {e}")
            await _play_next(chat_id)  # این یکی خراب بود، بعدی را امتحان کن
            return
        await _set_now(chat_id, {
            **track,
            "state":        "playing",
            "panel_msg_id": prev.get("panel_msg_id") if prev else _last_panel.get(chat_id),
            "initiator_id": prev.get("initiator_id") if prev else None,
            "path":         path,
        })
        _cancel_autoleave(chat_id)
        await _emit_panel(chat_id)
    else:
        # صف خالی است → بیکار شو و تایمرِ خروج خودکار را بگذار
        await _clear_now(chat_id)
        await _emit_panel(chat_id)
        _schedule_autoleave(chat_id)


async def _cmd_pause(chat_id: int):
    try:
        await calls.pause(chat_id)
    except Exception:
        pass
    now = await _get_now(chat_id)
    if now:
        now["state"] = "paused"
        await _set_now(chat_id, now)
    await _emit_panel(chat_id)


async def _cmd_resume(chat_id: int):
    try:
        await calls.resume(chat_id)
    except Exception:
        pass
    now = await _get_now(chat_id)
    if now:
        now["state"] = "playing"
        await _set_now(chat_id, now)
    await _emit_panel(chat_id)


async def _cmd_skip(chat_id: int):
    """ردکردن ترکِ فعلی: اگر صف چیزی دارد، بعدی؛ وگرنه پایان و خروج."""
    if await _queue_len(chat_id) > 0:
        await _play_next(chat_id)
    else:
        await _leave(chat_id, "⏭ آهنگ بعدی‌ای در صف نبود؛ از ویس‌چت خارج شدم.")


async def _cmd_stop(chat_id: int):
    """پایانِ کامل: صف را خالی کن و از ویس‌چت خارج شو."""
    await r.delete(queue_key(chat_id))
    await _leave(chat_id, "⛔ پخش پایان یافت و از ویس‌چت خارج شدم.")


async def _leave(chat_id: int, toast: str = ""):
    now = await _get_now(chat_id)
    if now:
        _cleanup_file(now.get("path"))
    try:
        await calls.leave_call(chat_id)
    except Exception:
        pass
    await _clear_now(chat_id)
    _cancel_autoleave(chat_id)
    await _emit_panel(chat_id)
    if toast:
        await _emit_toast(chat_id, toast)


# ════════════════════════════════════════════════════════════
#  خروج خودکار پس از ۳ دقیقه بیکاری
# ════════════════════════════════════════════════════════════
def _schedule_autoleave(chat_id: int):
    _cancel_autoleave(chat_id)

    async def _waiter():
        try:
            await asyncio.sleep(IDLE_TIMEOUT)
            # اگر هنوز هیچ آهنگی پخش نمی‌شود، خارج شو
            if not await _get_now(chat_id):
                await _leave(chat_id, "🌙 به‌خاطر بیکاری، از ویس‌چت خارج شدم.")
        except asyncio.CancelledError:
            pass

    _autoleave_tasks[chat_id] = asyncio.create_task(_waiter())


def _cancel_autoleave(chat_id: int):
    task = _autoleave_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


# ════════════════════════════════════════════════════════════
#  پایانِ طبیعیِ استریم → پخشِ بعدی
# ════════════════════════════════════════════════════════════
@calls.on_update()
async def _on_update(_, update):
    # وقتی یک ترک به‌طور طبیعی تمام شد
    if isinstance(update, StreamEnded):
        await _play_next(update.chat_id)


# ════════════════════════════════════════════════════════════
#  شنوندهٔ دستورهای Redis
# ════════════════════════════════════════════════════════════
async def _command_listener():
    pubsub = r.pubsub()
    await pubsub.subscribe(CMD_CHANNEL)
    print("👂 Userbot listening for music commands...")

    async for raw in pubsub.listen():
        if raw.get("type") != "message":
            continue
        data = unpack(raw["data"])
        action  = data.get("action")
        chat_id = data.get("chat_id")
        if chat_id is None:
            continue

        # هر دستور در تسکِ جدا اجرا می‌شود تا شنونده هیچ‌وقت بلاک نشود
        if action == "play":
            asyncio.create_task(_cmd_play(data))
        elif action == "pause":
            asyncio.create_task(_cmd_pause(chat_id))
        elif action == "resume":
            asyncio.create_task(_cmd_resume(chat_id))
        elif action == "skip":
            asyncio.create_task(_cmd_skip(chat_id))
        elif action == "stop":
            asyncio.create_task(_cmd_stop(chat_id))


# ════════════════════════════════════════════════════════════
#  راه‌اندازی
# ════════════════════════════════════════════════════════════
async def main():
    _sweep_stale_downloads()
    await client.start()
    await calls.start()
    print("✅ Userbot + PyTgCalls started.")
    await _command_listener()


if __name__ == "__main__":
    asyncio.run(main())