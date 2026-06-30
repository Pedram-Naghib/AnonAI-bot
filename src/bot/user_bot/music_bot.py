"""
یوزربات موزیک یکپارچه (In-Memory Mode) — سازگار با py-tgcalls==2.3.3 و Telethon.

اصلاحِ مهمِ این نسخه (رفعِ خطای cross-event-loop):
  در نسخه‌ی قبلی، `client = TelegramClient(...)` و `calls = PyTgCalls(client)`
  در سطحِ ماژول (هنگام import) ساخته می‌شدند. این import قبل از اجرای
  `asyncio.run(start_bot())` در main.py رخ می‌دهد، یعنی هنوز event loop اصلی
  ساخته نشده. py-tgcalls/ntgcalls در زمانِ ساخته‌شدن به یک loop بایند می‌شود،
  و بعداً `calls.play()` روی loopِ دیگری اجرا می‌شد →
  خطای «got Future attached to a different loop» و شکستِ هر پخش.

  حالا client و calls «درونِ» start_music_client (روی همان loopِ در حالِ اجرا)
  ساخته می‌شوند و هندلرِ on_update هم همان‌جا ثبت می‌شود.
"""

import os
import asyncio
import traceback

from telethon import TelegramClient
from telethon.sessions import StringSession

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, StreamEnded
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError

from telebot.async_telebot import AsyncTeleBot

from src.bot.music_protocol import (
    get_now, set_now, clear_now, get_queue_len,
    push_to_queue, pop_from_queue, clear_queue, IDLE_TIMEOUT
)

# ── پیکربندی ──────────────────────────────────────────────
API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
DOWNLOAD_DIR = "downloads"
_STRING_SESSION = os.getenv("USERBOT_SESSION", "").strip()

# 🌟 این‌ها دیگر در زمانِ import ساخته نمی‌شوند؛ در start_music_client مقداردهی می‌شوند.
client: TelegramClient = None
calls:  PyTgCalls = None

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
        get_queue_len(chat_id),
        now.get("performer", ""),
        now.get("duration", 0),
        now.get("with_video", False),
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
#  «نقل‌مکانِ» پنل به یک پیامِ تازه (برای دستورِ «پنل»)
#  وقتی کاربر دوباره پنل را احضار می‌کند، یک پیامِ جدید فرستاده می‌شود و
#  از این به بعد باید همان پیامِ جدید (نه پیامِ قدیمیِ گم‌شده در چت) آپدیت شود.
# ════════════════════════════════════════════════════════════
def repoint_panel(chat_id: int, new_panel_msg_id: int):
    """پنلِ فعال را به یک پیامِ تازه منتقل می‌کند تا آپدیت‌های بعدی روی آن انجام شود."""
    _last_panel[chat_id] = new_panel_msg_id
    now = get_now(chat_id)
    if now:
        now["panel_msg_id"] = new_panel_msg_id
        set_now(chat_id, now)


async def refresh_panel(chat_id: int):
    """آپدیتِ دستیِ پنلِ فعلی (نسخهٔ عمومیِ _emit_panel برای استفاده در هندلرها)."""
    await _emit_panel(chat_id)


# ════════════════════════════════════════════════════════════
#  دانلودِ صوت (فالبک؛ مسیرِ اصلی، دانلودِ سمتِ ربات است)
# ════════════════════════════════════════════════════════════
async def _download_audio(chat_id: int, msg_id: int) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    try:
        await client.get_entity(chat_id)
    except Exception as e:
        print(f"💥 entity resolve failed for {chat_id}: {e}")
        raise ValueError("ENTITY_NOT_FOUND: یوزربات این گروه را در کش خود ندارد.")

    msg = None
    last_err = None
    for attempt, delay in enumerate((0, 0.7, 1.5, 2.5), start=1):
        if delay:
            await asyncio.sleep(delay)
        try:
            msg = await client.get_messages(chat_id, ids=msg_id)
        except Exception as e:
            last_err = e
            print(f"💥 get_messages attempt {attempt} failed for {chat_id}/{msg_id}: {e}")
            continue
        if msg:
            break

    if last_err and not msg:
        raise ValueError(f"GET_MESSAGE_FAILED: {last_err}")
    if not msg:
        raise ValueError("MESSAGE_NOT_FOUND: پیام صوتی پیدا نشد.")

    try:
        path = await client.download_media(msg, file=os.path.join(DOWNLOAD_DIR, f"{chat_id}_{msg_id}"))
    except Exception as e:
        print(f"💥 download_media failed for {chat_id}/{msg_id}: {e}")
        raise ValueError(f"DOWNLOAD_MEDIA_FAILED: {e}")

    if not path:
        raise ValueError("DOWNLOAD_EMPTY: download_media مسیر خالی برگرداند.")
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
#  جست‌وجو و دانلود از یوتیوب (برای دستورِ «پخش <اسم آهنگ>»)
#  از yt-dlp استفاده می‌کند که عملیاتِ همزمان/مسدودکننده دارد،
#  پس همیشه داخلِ run_in_executor اجرا می‌شود تا event loop اصلی
#  (که Telethon/PyTgCalls هم روی همان اجرا می‌شوند) بلاک نشود.
#
#  ── نکتهٔ مهم دربارهٔ خطای «Sign in to confirm you're not a bot» ──
#  این خطا از سمتِ خودِ یوتیوب می‌آید (نه باگِ این پروژه): یوتیوب
#  ترافیکِ سرورها/دیتاسنترها (مثلِ Render) را به‌عنوانِ «ربات» تشخیص
#  می‌دهد و درخواست را رد می‌کند. تنها راهِ قابل‌اعتماد، فرستادنِ
#  کوکیِ یک حسابِ واقعیِ یوتیوب همراهِ درخواست است.
#
#  دو راه برای دادنِ کوکی به ربات وجود دارد:
#   ۱) فایل: یک فایلِ cookies.txt (فرمتِ Netscape) از مرورگرِ خودت
#      اکسپورت کن (افزونهٔ «Get cookies.txt LOCALLY») و در مسیرِ
#      YT_COOKIES_FILE (پیش‌فرض: yt_cookies.txt کنارِ پروژه) بگذار.
#      این روش وقتی سرور یک دیسکِ پایدار/قابلِ آپلود داشته باشد خوب است.
#   ۲) متغیرِ محیطی: کلِ محتوای فایلِ cookies.txt را کپی کن و در
#      متغیرِ محیطیِ YT_COOKIES_CONTENT بچسبان (مثلاً در پنلِ Render).
#      این روش برای Render توصیه می‌شود چون نیازی به دیسکِ پایدار یا
#      آپلودِ دستیِ فایل ندارد — کوکی همراهِ بقیهٔ env varها ست می‌شود
#      و در زمانِ استارت، خودکار به یک فایلِ موقت نوشته می‌شود.
# ════════════════════════════════════════════════════════════
COOKIES_FILE = os.getenv("YT_COOKIES_FILE", "").strip() or "yt_cookies.txt"


def _ensure_cookies_file_from_env():
    """
    اگر YT_COOKIES_CONTENT ست شده باشد، محتوای آن را یک‌بار (در زمانِ
    import) در مسیرِ COOKIES_FILE می‌نویسد تا yt-dlp بتواند از آن
    به‌عنوانِ cookiefile معمولی استفاده کند. env var اولویت دارد —
    یعنی اگر هم فایل دستی گذاشته شده و هم env var ست شده، env var
    آن را بازنویسی می‌کند (منبعِ واحدِ صحت همان چیزی است که در
    تنظیماتِ Render ست شده).
    """
    content = os.getenv("YT_COOKIES_CONTENT", "").strip()
    if not content:
        return
    try:
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(content + "\n")
        print(f"🍪 yt-dlp cookies written from YT_COOKIES_CONTENT → {COOKIES_FILE}")
    except Exception as e:
        print(f"⚠️ Failed to write cookies file from YT_COOKIES_CONTENT: {e}")


_ensure_cookies_file_from_env()


def _yt_dlp_search_sync(query: str) -> dict:
    import yt_dlp

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    out_template = os.path.join(DOWNLOAD_DIR, "yt_%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "default_search": "ytsearch1",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
        }],
        # یک نتیجه‌ی واحد و کوتاه — جلوگیری از دانلودِ ویدیوهای چندساعته به اشتباه
        "match_filter": yt_dlp.utils.match_filter_func("duration < 1800"),
        # کلاینتِ android معمولاً دیرتر از کلاینتِ وب به چالشِ ضدِ-رباتِ یوتیوب
        # برمی‌خورد؛ این یک خطِ دفاعیِ اول است (بدون نیاز به کوکی)، نه تضمین.
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }

    if os.path.isfile(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=True)
        # وقتی default_search فعال است، نتیجه درونِ entries قرار می‌گیرد
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise ValueError("NO_RESULTS: نتیجه‌ای برای این جست‌وجو پیدا نشد.")
            info = entries[0]
        final_path = ydl.prepare_filename(info)
        # پسوندِ واقعی پس از تبدیلِ پسا-پردازشی ممکن است opus باشد، نه پسوندِ اصلی
        base, _ = os.path.splitext(final_path)
        opus_path = base + ".opus"
        if os.path.exists(opus_path):
            final_path = opus_path

        return {
            "path":      final_path,
            "title":     info.get("title") or "آهنگ ناشناس",
            "performer": info.get("uploader") or "",
            "duration":  int(info.get("duration") or 0),
        }


async def search_and_download_youtube(query: str) -> dict:
    """
    جست‌وجوی «query» در یوتیوب و دانلودِ بهترین تطابقِ صوتی.
    خروجی: {"path", "title", "performer", "duration"}
    در صورتِ نبودِ نتیجه یا خطا، Exception با پیامِ قابل‌نمایش raise می‌شود
    (پیشوندهای ممکن: NO_RESULTS، YT_BOT_CHECK، YTDLP_FAILED).
    """
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _yt_dlp_search_sync, query)
    except Exception as e:
        msg = str(e)
        if "NO_RESULTS" in msg:
            raise ValueError("NO_RESULTS: نتیجه‌ای برای این جست‌وجو پیدا نشد.")
        if "Sign in to confirm" in msg or "not a bot" in msg:
            raise ValueError(
                "YT_BOT_CHECK: یوتیوب این درخواست را به‌عنوانِ ربات تشخیص داده. "
                "نیاز به فایلِ کوکیِ یک حسابِ واقعیِ یوتیوب روی سرور دارد."
            )
        print(f"💥 yt-dlp search/download failed for '{query}': {e}")
        raise ValueError(f"YTDLP_FAILED: {msg[:200]}")


# ════════════════════════════════════════════════════════════
#  منطقِ پخش / صف (py-tgcalls 2.3.3)
# ════════════════════════════════════════════════════════════
async def _start_stream(chat_id: int, track: dict) -> str:
    # اولویت با فایلی است که خودِ ربات رسمی دانلود کرده و مسیرش را داده.
    path = track.get("audio_path")
    if not (path and os.path.exists(path)):
        path = await _download_audio(track["audio_chat_id"], track["audio_msg_id"])

    # video_flags=IGNORE یعنی فقط صدا پخش می‌شود (حالتِ پیش‌فرض، سازگار با قبل).
    # وقتی track["with_video"] صراحتاً True باشد، پرچم حذف می‌شود تا py-tgcalls
    # تصویرِ فایل را هم تشخیص داده و به‌صورتِ ویدیوچت پخش کند.
    video_flags = MediaStream.Flags.AUTO_DETECT if track.get("with_video") else MediaStream.Flags.IGNORE

    try:
        await calls.play(
            chat_id,
            MediaStream(path, video_flags=video_flags),
        )
    except Exception:
        _cleanup_file(path)
        raise
    return path


async def cmd_play(chat_id: int, audio_chat_id: int, audio_msg_id: int, title: str,
                   requester_id: int, initiator_id: int, panel_msg_id: int,
                   audio_path: str = None, performer: str = "", duration: int = 0,
                   with_video: bool = False):
    if calls is None:
        await _emit_toast(chat_id, "⚠️ موتور موزیک هنوز آماده نیست؛ چند لحظه بعد دوباره امتحان کن.")
        return

    track = {
        "audio_chat_id": audio_chat_id,
        "audio_msg_id":  audio_msg_id,
        "title":         title,
        "performer":     performer,
        "duration":      duration,
        "requester_id":  requester_id,
        "audio_path":    audio_path,
        "with_video":    with_video,
    }
    now = get_now(chat_id)

    # ── حالتِ ۱: چیزی در حال پخش/مکث است → آهنگ به صف می‌رود ──
    if now and now.get("state") in ("playing", "paused"):
        pos = push_to_queue(chat_id, track)
        # پیامِ «در حال اتصال…»‌ای که تازه ساخته شده را به یک رسیدِ «به صف اضافه شد»
        # تبدیل می‌کنیم تا پیامِ سرگردان و گمراه‌کننده در چت نماند.
        try:
            from src.bot.handlers.userbot_cmds import build_queue_added
            await _bot_instance.edit_message_text(
                build_queue_added(title, performer, duration, pos),
                chat_id, panel_msg_id, parse_mode="HTML"
            )
        except Exception:
            await _emit_toast(chat_id, f"🎵 «{title}» به صف اضافه شد (موقعیت {pos}).")
        # پنلِ اصلیِ «در حال پخش» را هم رفرش می‌کنیم تا تعدادِ صف به‌روز شود.
        await _emit_panel(chat_id)
        return

    # ── حالتِ ۲: چیزی پخش نمی‌شود → همین آهنگ همین حالا پخش می‌شود ──
    _last_panel[chat_id] = panel_msg_id
    try:
        path = await _start_stream(chat_id, track)
    except NoActiveGroupCall:
        await _emit_toast(chat_id, "⚠️ ابتدا یک ویس‌چت در گروه ایجاد کنید، سپس دوباره «پخش» را بزنید.")
        return
    except ValueError as e:
        reason = str(e)
        if reason.startswith("ENTITY_NOT_FOUND"):
            await _emit_toast(chat_id, "⚠️ یوزربات این گروه را نمی‌شناسد. مطمئن شو یوزربات عضو گروه است و سرویس را ری‌استارت کن.")
        elif reason.startswith("MESSAGE_NOT_FOUND"):
            await _emit_toast(chat_id, "⚠️ فایل صوتی در دسترس نبود. دوباره روی یک فایل صوتی تازه ریپلای کن.")
        else:
            await _emit_toast(chat_id, f"⚠️ خطا در آماده‌سازی فایل:\n<code>{reason}</code>")
        print(f"💥 play ValueError in {chat_id}: {reason}")
        return
    except Exception as e:
        # چاپِ کاملِ خطا برای دیباگ (نوع + متن + traceback)
        print(f"💥 play error in {chat_id}: {type(e).__name__}: {e}")
        traceback.print_exc()
        await _emit_toast(
            chat_id,
            "⚠️ اتصال به ویس‌چت ناموفق بود.\n"
            "۱) یوزربات باید عضو گروه باشد.\n"
            "۲) ویس‌چت گروه باید از قبل باز باشد.\n"
            f"<code>{type(e).__name__}: {str(e)[:200]}</code>"
        )
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


async def _leave(chat_id: int, toast: str = ""):
    now = get_now(chat_id)
    if now:
        _cleanup_file(now.get("path"))
    if calls is not None:
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
async def _on_update(_, update):
    if isinstance(update, StreamEnded) and update.stream_type == StreamEnded.Type.AUDIO:
        await _play_next(update.chat_id)


# ════════════════════════════════════════════════════════════
#  راه‌اندازی — client و calls اینجا (روی loopِ در حالِ اجرا) ساخته می‌شوند
# ════════════════════════════════════════════════════════════
async def start_music_client(bot_instance: AsyncTeleBot):
    global _bot_instance, client, calls
    _bot_instance = bot_instance

    if not API_ID or not API_HASH:
        print("⚠️ API_ID/API_HASH تنظیم نشده‌اند — موتور موزیک غیرفعال ماند.")
        return

    # تضمینِ ffmpeg (py-tgcalls برای پخشِ فایل به ffmpeg نیاز دارد)
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception as e:
        print(f"⚠️ static_ffmpeg setup skipped: {e}")

    # 🌟 ساختِ کلاینت‌ها روی همین loopِ در حالِ اجرا (نه در زمانِ import)
    if _STRING_SESSION:
        print("🔑 Using StringSession from env (USERBOT_SESSION).")
        client = TelegramClient(StringSession(_STRING_SESSION), API_ID, API_HASH)
    else:
        print("🔑 Using file session: userbot.session")
        client = TelegramClient("userbot", API_ID, API_HASH)

    calls = PyTgCalls(client)
    calls.on_update()(_on_update)  # ثبتِ هندلرِ پایانِ استریم به‌صورتِ برنامه‌ای

    _sweep_stale_downloads()
    try:
        await client.start()
        await calls.start()
        me = await client.get_me()
        print(f"✅ Userbot + PyTgCalls started (2.3.3). Logged in as: {getattr(me, 'username', None) or me.id}")

        # کشِ entity همه‌ی چت‌ها تا get_messages/فالبک روی گروه‌های عضو کار کند
        dialog_count = 0
        async for _dialog in client.iter_dialogs():
            dialog_count += 1
        print(f"📚 Cached {dialog_count} dialogs/entities for the userbot session.")

    except Exception as e:
        print(f"💥 Music client failed to start: {e}")
        traceback.print_exc()