"""
حافظه موقت درون‌برنامه‌ای (In-Memory State) برای سیستم موزیک ویس‌چت.

این فایل هستهٔ مدیریتِ وضعیت و صف آهنگ‌هاست. ربات رسمی (Telebot) و
یوزربات (Telethon) در یک پروسهٔ مشترک روی همین دیکشنری‌ها کار می‌کنند.
"""

import random

# ── مدت بیکاری مجاز پیش از خروج خودکار (ثانیه) ─────────────
IDLE_TIMEOUT = 180  # ۳ دقیقه

# ── حالت‌های Loop ────────────────────────────────────────────
LOOP_NONE  = "none"
LOOP_TRACK = "track"   # تکرارِ یک آهنگ
LOOP_QUEUE = "queue"   # تکرارِ کل صف

# ── ساختارهای داده درون‌حافظه‌ای (RAM) ──────────────────────
_music_now:     dict = {}   # {chat_id: track_info_dict}
_music_queue:   dict = {}   # {chat_id: [track_dict, ...]}
_music_history: dict = {}   # {chat_id: [track_dict, ...]}  (آخرین ۲۰ تا)
_music_loop:    dict = {}   # {chat_id: "none"|"track"|"queue"}
_music_volume:  dict = {}   # {chat_id: int 1-100} — همیشه ولومِ «هدف»، صفر نمی‌شود
_music_muted:   dict = {}   # {chat_id: bool} — بی‌صدا بودن جدا از عددِ ولوم نگه داشته می‌شود،
                             # چون تلگرام volume=0 را نامعتبر می‌داند و بی‌صدا شدن باید از
                             # طریقِ فلگِ muted خودِ API انجام شود، نه صفر کردنِ ولوم.

HISTORY_MAX = 20
VOLUME_DEFAULT = 100
VOLUME_STEP    = 10


# ════════════════════════════════════════════════════════════
#  Now Playing
# ════════════════════════════════════════════════════════════
def get_now(chat_id: int) -> dict:
    return _music_now.get(chat_id, {})


def set_now(chat_id: int, data: dict):
    _music_now[chat_id] = data


def clear_now(chat_id: int):
    _music_now.pop(chat_id, None)


# ════════════════════════════════════════════════════════════
#  Queue
# ════════════════════════════════════════════════════════════
def get_queue_len(chat_id: int) -> int:
    return len(_music_queue.get(chat_id, []))


def peek_queue(chat_id: int) -> list:
    """فقط خواندن — صف را تغییر نمی‌دهد."""
    return list(_music_queue.get(chat_id, []))


def push_to_queue(chat_id: int, track: dict) -> int:
    """اضافه به انتهای صف. موقعیت (۱-based) را برمی‌گرداند."""
    _music_queue.setdefault(chat_id, []).append(track)
    return len(_music_queue[chat_id])


def push_to_front_queue(chat_id: int, track: dict):
    """درج در ابتدای صف — «پخش بعدی این باشه»."""
    _music_queue.setdefault(chat_id, []).insert(0, track)


def pop_from_queue(chat_id: int) -> dict:
    q = _music_queue.get(chat_id)
    if q:
        return q.pop(0)
    return {}


def clear_queue(chat_id: int):
    _music_queue[chat_id] = []


def shuffle_queue(chat_id: int):
    """قاطی کردنِ ترتیبِ صفِ فعلی."""
    q = _music_queue.get(chat_id)
    if q and len(q) > 1:
        random.shuffle(q)


# ════════════════════════════════════════════════════════════
#  Loop
# ════════════════════════════════════════════════════════════
def get_loop(chat_id: int) -> str:
    return _music_loop.get(chat_id, LOOP_NONE)


def cycle_loop(chat_id: int) -> str:
    """چرخشِ حالت Loop: none → track → queue → none. مقدارِ جدید را برمی‌گرداند."""
    current = get_loop(chat_id)
    next_mode = {LOOP_NONE: LOOP_TRACK, LOOP_TRACK: LOOP_QUEUE, LOOP_QUEUE: LOOP_NONE}[current]
    _music_loop[chat_id] = next_mode
    return next_mode


# ════════════════════════════════════════════════════════════
#  Volume
# ════════════════════════════════════════════════════════════
def get_volume(chat_id: int) -> int:
    return _music_volume.get(chat_id, VOLUME_DEFAULT)


def set_volume(chat_id: int, volume: int) -> int:
    v = max(1, min(100, volume))  # تلگرام volume=0 را «نامعتبر» رد می‌کند — کف همیشه ۱ است
    _music_volume[chat_id] = v
    return v


def adjust_volume(chat_id: int, delta: int) -> int:
    return set_volume(chat_id, get_volume(chat_id) + delta)


def is_muted(chat_id: int) -> bool:
    return _music_muted.get(chat_id, False)


def toggle_mute(chat_id: int) -> bool:
    """بی‌صدا/صدادار می‌کند (toggle). حالتِ جدید را برمی‌گرداند."""
    muted = not is_muted(chat_id)
    _music_muted[chat_id] = muted
    return muted


def unmute(chat_id: int):
    _music_muted[chat_id] = False


# ════════════════════════════════════════════════════════════
#  History
# ════════════════════════════════════════════════════════════
def push_to_history(chat_id: int, track: dict):
    h = _music_history.setdefault(chat_id, [])
    # جلوگیری از تکرارِ متوالیِ همان آهنگ
    if h and h[0].get("audio_msg_id") == track.get("audio_msg_id"):
        return
    h.insert(0, track)
    if len(h) > HISTORY_MAX:
        h.pop()


def get_history(chat_id: int) -> list:
    return list(_music_history.get(chat_id, []))