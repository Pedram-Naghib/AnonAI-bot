"""
یوزربات موزیک یکپارچه (In-Memory Mode) — سازگار با py-tgcalls==2.3.3 و Telethon.

client و calls درونِ start_music_client (روی همان loopِ در حالِ اجرا) ساخته
می‌شوند تا از خطای cross-event-loop جلوگیری شود.
"""

import os
import asyncio
import traceback

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.functions.phone import EditGroupCallParticipantRequest, GetGroupParticipantsRequest
from telethon.tl.types import InputPeerSelf, Channel, Chat

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, StreamEnded
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError

from telebot.async_telebot import AsyncTeleBot

from src.bot.music_protocol import (
    get_now, set_now, clear_now, get_queue_len,
    push_to_queue, push_to_front_queue, pop_from_queue, clear_queue,
    shuffle_queue, get_loop, cycle_loop,
    get_volume, set_volume, adjust_volume, is_muted, toggle_mute, unmute,
    push_to_history, get_history,
    IDLE_TIMEOUT, LOOP_NONE, LOOP_TRACK, LOOP_QUEUE,
)

# ── پیکربندی ──────────────────────────────────────────────
API_ID          = int(os.getenv("API_ID", "0"))
API_HASH        = os.getenv("API_HASH", "")
DOWNLOAD_DIR    = "downloads"
_STRING_SESSION = os.getenv("USERBOT_SESSION", "").strip()

client: TelegramClient = None
calls:  PyTgCalls       = None

_autoleave_tasks: dict = {}
_last_panel:      dict = {}
_bot_instance           = None


# ════════════════════════════════════════════════════════════
#  ارسال رویداد به ربات رسمی
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
        get_queue_len(chat_id),
        now.get("performer", ""),
        now.get("duration", 0),
        now.get("with_video", False),
        now.get("requester_id"),
        now.get("requester_name", ""),
        get_loop(chat_id),
        get_volume(chat_id),
        is_muted(chat_id),
    )
    try:
        await _bot_instance.edit_message_text(
            text, chat_id, now.get("panel_msg_id"),
            parse_mode="HTML", reply_markup=kb
        )
    except Exception as e:
        print(f"⚠️ _emit_panel edit failed for {chat_id}: {type(e).__name__}: {e}")


async def _emit_toast(chat_id: int, text: str):
    if not _bot_instance:
        return
    try:
        await _bot_instance.send_message(chat_id, text, parse_mode="HTML")
    except Exception:
        pass


# ════════════════════════════════════════════════════════════
#  نقل‌مکانِ هاب و رفرش
# ════════════════════════════════════════════════════════════
def repoint_panel(chat_id: int, new_panel_msg_id: int):
    """هاب را به پیامِ تازه منتقل می‌کند."""
    _last_panel[chat_id] = new_panel_msg_id
    now = get_now(chat_id)
    if now:
        now["panel_msg_id"] = new_panel_msg_id
        set_now(chat_id, now)


async def refresh_panel(chat_id: int):
    await _emit_panel(chat_id)


# ════════════════════════════════════════════════════════════
#  دانلود صوت (فالبک از طریق یوزربات)
# ════════════════════════════════════════════════════════════
async def _download_audio(chat_id: int, msg_id: int) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    try:
        await client.get_entity(chat_id)
    except Exception as e:
        raise ValueError(f"ENTITY_NOT_FOUND: {e}")

    msg = None
    last_err = None
    for attempt, delay in enumerate((0, 0.7, 1.5, 2.5), start=1):
        if delay:
            await asyncio.sleep(delay)
        try:
            msg = await client.get_messages(chat_id, ids=msg_id)
        except Exception as e:
            last_err = e
            continue
        if msg:
            break

    if not msg:
        raise ValueError(f"GET_MESSAGE_FAILED: {last_err}")

    try:
        path = await client.download_media(
            msg, file=os.path.join(DOWNLOAD_DIR, f"{chat_id}_{msg_id}")
        )
    except Exception as e:
        raise ValueError(f"DOWNLOAD_MEDIA_FAILED: {e}")

    if not path:
        raise ValueError("DOWNLOAD_EMPTY")
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
#  منطقِ پخش (py-tgcalls 2.3.3)
# ════════════════════════════════════════════════════════════
async def _start_stream(chat_id: int, track: dict) -> str:
    path = track.get("audio_path")
    if not (path and os.path.exists(path)):
        path = await _download_audio(track["audio_chat_id"], track["audio_msg_id"])

    video_flags = (
        MediaStream.Flags.AUTO_DETECT if track.get("with_video")
        else MediaStream.Flags.IGNORE
    )
    try:
        await calls.play(chat_id, MediaStream(path, video_flags=video_flags))
    except Exception:
        _cleanup_file(path)
        raise

    # تنظیمِ ولوم/بی‌صدایِ ذخیره‌شده برای این گروه. نکته‌ی مهم: جوین‌شدنِ
    # یوزربات به ویس‌چت ظاهراً همیشه با muted=True شروع می‌شه (پیش‌فرضِ
    # pytgcalls برای این الگوی استریم) — پس همیشه صریحاً muted رو ست می‌کنیم،
    # نه فقط وقتی خودمون فکر می‌کنیم قبلاً میوت بوده.
    try:
        if is_muted(chat_id):
            await _edit_own_participant(chat_id, muted=True)
        else:
            await _edit_own_participant(chat_id, muted=False, volume=get_volume(chat_id))
    except Exception as e:
        print(f"⚠️ volume/mute-on-start failed: {type(e).__name__}: {e}")

    return path


async def cmd_play(chat_id: int, audio_chat_id: int, audio_msg_id: int, title: str,
                   requester_id: int, initiator_id: int, panel_msg_id: int,
                   audio_path: str = None, performer: str = "", duration: int = 0,
                   with_video: bool = False, file_unique_id: str = "",
                   requester_name: str = ""):
    if calls is None:
        await _emit_toast(chat_id, "⚠️ موتور موزیک هنوز آماده نیست؛ چند لحظه بعد دوباره امتحان کن.")
        return

    track = {
        "audio_chat_id":  audio_chat_id,
        "audio_msg_id":   audio_msg_id,
        "title":          title,
        "performer":      performer,
        "duration":       duration,
        "requester_id":   requester_id,
        "requester_name": requester_name,
        "audio_path":     audio_path,
        "with_video":     with_video,
        "file_unique_id": file_unique_id,
    }
    now = get_now(chat_id)

    # حالتِ ۱: چیزی در حال پخش/مکث است → صف
    if now and now.get("state") in ("playing", "paused"):
        pos = push_to_queue(chat_id, track)
        # دکمه‌های «پخش بعدی این باشه / همین ترتیب خوبه» فقط وقتی معنی دارند
        # که صف بیشتر از یک آهنگ داشته باشد — اگر این تنها آهنگِ صف باشد
        # (pos == 1) به‌هرحال همان بعدی پخش می‌شود و پرسیدن لازم نیست.
        kb = _queue_added_keyboard(chat_id, pos - 1) if pos > 1 else None
        try:
            from src.bot.handlers.userbot_cmds import build_queue_added
            await _bot_instance.edit_message_text(
                build_queue_added(title, performer, duration, pos),
                chat_id, panel_msg_id, parse_mode="HTML",
                reply_markup=kb
            )
        except Exception:
            await _emit_toast(chat_id, f"🎵 «{title}» به صف اضافه شد (موقعیت {pos}).")
        await _emit_panel(chat_id)
        return

    # حالتِ ۲: پخش نمی‌شود → همین حالا پخش
    _last_panel[chat_id] = panel_msg_id
    try:
        path = await _start_stream(chat_id, track)
    except NoActiveGroupCall:
        await _emit_toast(chat_id, "⚠️ ابتدا یک ویس‌چت در گروه باز کنید، سپس دوباره «پخش» بزنید.")
        return
    except ValueError as e:
        reason = str(e)
        if "ENTITY_NOT_FOUND" in reason:
            msg = "⚠️ یوزربات این گروه را نمی‌شناسد. مطمئن شو عضو گروه است و سرویس را ری‌استارت کن."
        elif "MESSAGE_NOT_FOUND" in reason or "GET_MESSAGE" in reason:
            msg = "⚠️ فایل صوتی پیدا نشد. دوباره روی یک فایل تازه ریپلای کن."
        else:
            msg = f"⚠️ خطا:\n<code>{reason}</code>"
        await _emit_toast(chat_id, msg)
        return
    except Exception as e:
        traceback.print_exc()
        await _emit_toast(chat_id,
            f"⚠️ اتصال به ویس‌چت ناموفق بود.\n<code>{type(e).__name__}: {str(e)[:200]}</code>")
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


def _queue_added_keyboard(chat_id: int, queue_idx: int):
    """کیبوردِ «پخش بعدی این باشه؟» زیرِ پیامِ اضافه‌شدن به صف."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(
            "▶️ پخش بعدی این باشه",
            callback_data=f"mus_playnext_{queue_idx}"
        ),
        InlineKeyboardButton(
            "✅ همین ترتیب خوبه",
            callback_data="mus_queue_ok"
        ),
    )
    return kb


async def _play_next(chat_id: int):
    prev = get_now(chat_id)
    if prev:
        push_to_history(chat_id, prev)

    loop_mode = get_loop(chat_id)

    # Loop Track: همان آهنگ را دوباره پخش کن
    if loop_mode == LOOP_TRACK and prev:
        # audio_path فایلِ دیسکی است که احتمالاً در پخشِ قبلی پاک شده —
        # حذفش می‌کنیم تا _start_stream مجبور بشه دوباره از یوزربات دانلود کنه.
        track_for_loop = {**prev, "audio_path": None}
        try:
            _cleanup_file(prev.get("path"))
            path = await _start_stream(chat_id, track_for_loop)
        except Exception as e:
            print(f"💥 loop-track error in {chat_id}: {e}")
            await _play_next_from_queue(chat_id, prev)
            return
        set_now(chat_id, {
            **track_for_loop,
            "state": "playing",
            "panel_msg_id": prev.get("panel_msg_id"),
            "initiator_id": prev.get("initiator_id"),
            "path":  path,
        })
        _cancel_autoleave(chat_id)
        await _emit_panel(chat_id)
        return

    # Loop Queue: وقتی صف خالی شد، کل صف را دوباره پر کن
    if loop_mode == LOOP_QUEUE and not get_queue_len(chat_id) and prev:
        push_to_queue(chat_id, {k: v for k, v in prev.items()
                                if k not in ("state", "panel_msg_id", "initiator_id", "path", "audio_path")})

    _cleanup_file(prev.get("path") if prev else None)
    await _play_next_from_queue(chat_id, prev)


async def _play_next_from_queue(chat_id: int, prev: dict):
    panel_msg_id = (prev.get("panel_msg_id") if prev else None) or _last_panel.get(chat_id)
    initiator_id = prev.get("initiator_id") if prev else None

    track = pop_from_queue(chat_id)
    if track:
        try:
            path = await _start_stream(chat_id, track)
        except Exception as e:
            print(f"💥 next-play error in {chat_id}: {e}")
            await _play_next_from_queue(chat_id, prev)
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
    else:
        clear_now(chat_id)
        await _emit_panel(chat_id)
        _schedule_autoleave(chat_id)


# ════════════════════════════════════════════════════════════
#  دستورهای کنترل
# ════════════════════════════════════════════════════════════
async def cmd_pause(chat_id: int):
    if calls is None:
        return
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
    if calls is None:
        return
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


async def cmd_shuffle(chat_id: int):
    shuffle_queue(chat_id)
    await _emit_panel(chat_id)


async def cmd_loop(chat_id: int) -> str:
    new_mode = cycle_loop(chat_id)
    await _emit_panel(chat_id)
    return new_mode


async def _get_group_call(chat_id: int):
    """InputGroupCall را مستقیم از خودِ تلگرام می‌گیرد، بدون تکیه به کشِ داخلیِ
    pytgcalls. گروه می‌تونه یا سوپرگروه/کانال باشه (GetFullChannelRequest) یا
    یه گروهِ معمولیِ قدیمی (GetFullChatRequest) — این دو تا API کاملاً جدا
    هستن تو تلگرام، برای همینم اول نوعِ entity رو تشخیص می‌دیم."""
    entity = await client.get_entity(chat_id)
    if isinstance(entity, Channel):
        full = await client(GetFullChannelRequest(entity))
    elif isinstance(entity, Chat):
        full = await client(GetFullChatRequest(entity.id))
    else:
        raise NoActiveGroupCall()
    call = getattr(full.full_chat, "call", None)
    if call is None:
        raise NoActiveGroupCall()
    return call


async def _edit_own_participant(chat_id: int, muted: bool = None, volume: int = None):
    """تغییرِ ولوم/بی‌صدایِ خودمان (یوزربات) در ویس‌چت — مستقیم با
    EditGroupCallParticipantRequest و participant=InputPeerSelf، کاملاً
    مستقل از pytgcalls. volume باید ۱ تا ۲۰۰ باشد (خودِ تلگرام در ۲۰۰ سقف
    می‌گذارد)؛ ۰ را «نامعتبر» رد می‌کند، برای همین بی‌صدا شدن همیشه با
    muted=True انجام می‌شود، نه volume=0."""
    call = await _get_group_call(chat_id)
    kwargs = {}
    if muted is not None:
        kwargs["muted"] = muted
    if volume is not None:
        kwargs["volume"] = max(1, min(200, volume)) * 100
    await client(EditGroupCallParticipantRequest(
        call=call,
        participant=InputPeerSelf(),
        **kwargs,
    ))

    # تشخیصی: چون قبلاً دیده بودیم درخواست بدونِ خطا موفق می‌شد ولی هیچ اثری
    # نداشت، بلافاصله وضعیتِ خودمون رو از سرور می‌خونیم تا معلوم شه تلگرام
    # واقعاً ثبتش کرده یا نه، و اصلاً یوزربات به‌عنوانِ participant دیده می‌شه یا نه.
    try:
        parts = await client(GetGroupParticipantsRequest(
            call=call, ids=[InputPeerSelf()], sources=[], offset="", limit=1
        ))
        if parts.participants:
            p = parts.participants[0]
            print(f"🔎 self-participant after edit → muted={p.muted}, volume={p.volume}")
        else:
            print("🔎 self-participant after edit → NOT FOUND in call's participant list "
                  "(یوزربات اصلاً به‌عنوانِ participant ثبت نشده — یعنی ریشه‌ی مشکل همینه)")
    except Exception as e:
        print(f"🔎 participant verify failed: {type(e).__name__}: {e}")


async def cmd_volume(chat_id: int, delta: int) -> int:
    """ولوم را به اندازه‌ی delta تغییر می‌دهد. همیشه صریحاً muted=False هم می‌فرستد
    (نه فقط بر اساسِ حالتِ داخلیِ ما) چون فهمیدیم جوین‌شدنِ اولیه با muted=True
    اتفاق می‌افته و اگه اون فلگ رو صریحاً پاک نکنیم صدا اصلاً شنیده نمی‌شه.
    مقدارِ جدیدِ ولوم را برمی‌گرداند."""
    new_vol = adjust_volume(chat_id, delta)
    if calls is not None:
        try:
            unmute(chat_id)
            await _edit_own_participant(chat_id, muted=False, volume=new_vol)
        except Exception as e:
            print(f"⚠️ cmd_volume failed: {type(e).__name__}: {e}")
    await _emit_panel(chat_id)
    return new_vol


async def cmd_mute(chat_id: int) -> bool:
    """بی‌صدا/صدادار می‌کند (toggle). حالتِ جدید (True یعنی الان بی‌صداست) را برمی‌گرداند."""
    muted = toggle_mute(chat_id)
    if calls is not None:
        try:
            if muted:
                await _edit_own_participant(chat_id, muted=True)
            else:
                # موقعِ صدادار کردن، هم فلگِ muted رو برمی‌داریم هم ولومِ
                # ذخیره‌شده رو تو همون یک درخواست دوباره اعمال می‌کنیم
                await _edit_own_participant(chat_id, muted=False, volume=get_volume(chat_id))
        except Exception as e:
            print(f"⚠️ cmd_mute failed: {type(e).__name__}: {e}")
    await _emit_panel(chat_id)
    return muted


async def cmd_move_to_front(chat_id: int, queue_idx: int):
    """آیتمِ queue_idx را به اول صف می‌برد (پخش بعدی)."""
    from src.bot.music_protocol import _music_queue
    q = _music_queue.get(chat_id, [])
    if 0 <= queue_idx < len(q):
        track = q.pop(queue_idx)
        q.insert(0, track)
    await _emit_panel(chat_id)


async def _leave(chat_id: int, toast: str = ""):
    now = get_now(chat_id)
    if now:
        push_to_history(chat_id, now)
        _cleanup_file(now.get("path"))
        # panel_msg_id را قبل از clear_now نگه می‌داریم تا _emit_panel بتونه
        # همون پیامِ درست رو ویرایش کنه (بعد از clear_now، now خالیه)
        panel_msg_id = now.get("panel_msg_id")
        if panel_msg_id:
            _last_panel[chat_id] = panel_msg_id

    if calls is not None:
        try:
            await calls.leave_call(chat_id)
        except (NotInCallError, Exception):
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
async def _on_update(_, update):
    if isinstance(update, StreamEnded) and update.stream_type == StreamEnded.Type.AUDIO:
        await _play_next(update.chat_id)


# ════════════════════════════════════════════════════════════
#  راه‌اندازی
# ════════════════════════════════════════════════════════════
async def start_music_client(bot_instance: AsyncTeleBot):
    global _bot_instance, client, calls
    _bot_instance = bot_instance

    if not API_ID or not API_HASH:
        print("⚠️ API_ID/API_HASH تنظیم نشده‌اند — موتور موزیک غیرفعال ماند.")
        return

    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception as e:
        print(f"⚠️ static_ffmpeg setup skipped: {e}")

    if _STRING_SESSION:
        print("🔑 Using StringSession from env (USERBOT_SESSION).")
        client = TelegramClient(StringSession(_STRING_SESSION), API_ID, API_HASH)
    else:
        print("🔑 Using file session: userbot.session")
        client = TelegramClient("userbot", API_ID, API_HASH)

    calls = PyTgCalls(client)
    calls.on_update()(_on_update)

    _sweep_stale_downloads()
    try:
        await client.start()
        await calls.start()
        me = await client.get_me()
        print(f"✅ Userbot + PyTgCalls started (2.3.3). Logged in as: {getattr(me, 'username', None) or me.id}")

        dialog_count = 0
        async for _ in client.iter_dialogs():
            dialog_count += 1
        print(f"📚 Cached {dialog_count} dialogs/entities for the userbot session.")

    except Exception as e:
        print(f"💥 Music client failed to start: {e}")
        traceback.print_exc()