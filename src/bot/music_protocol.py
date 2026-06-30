"""
حافظه موقت درون‌برنامه‌ای (In-Memory State) برای سیستم موزیک ویس‌چت پروژه‌ی ServantBot.

با حذف کامل Redis، این فایل به عنوان هسته مدیریت وضعیت و صف آهنگ‌ها عمل می‌کند.
چون ربات رسمی (Telebot) و یوزربات (Telethon) در یک پروسه مشترک اجرا می‌شوند،
می‌توانند مستقیماً و بدون نیاز به واسطه، از این توابع برای هماهنگی استفاده کنند.
"""

# ── مدت بیکاری مجاز پیش از خروج خودکار (ثانیه) ─────────────
IDLE_TIMEOUT = 180  # ۳ دقیقه

# ── ساختارهای داده درون حافظه‌ای (RAM) ──────────────────────
# ساختار وضعیت فعلی: {chat_id: {track_info_dict}}
_music_now = {}

# ساختار صف آهنگ‌ها: {chat_id: [list_of_track_dicts]}
_music_queue = {}


# ── هِلپرهای مدیریت وضعیت در حال پخش (Now Playing) ──────────
def get_now(chat_id: int) -> dict:
    """گرفتن اطلاعات آهنگ در حال پخش در گروه."""
    return _music_now.get(chat_id, {})


def set_now(chat_id: int, data: dict):
    """تنظیم یا بروزرسانی وضعیت آهنگ در حال پخش."""
    _music_now[chat_id] = data


def clear_now(chat_id: int):
    """پاک کردن وضعیت در حال پخش گروه (هنگام پایان یا استاپ)."""
    if chat_id in _music_now:
        del _music_now[chat_id]


# ── هِلپرهای مدیریت صف (Queue Management) ──────────────────
def get_queue_len(chat_id: int) -> int:
    """تعداد آهنگ‌های موجود در صف گروه."""
    return len(_music_queue.get(chat_id, []))


def peek_queue(chat_id: int) -> list:
    """
    گرفتنِ لیستِ آهنگ‌های صف بدونِ تغییر دادنِ صف (فقط خواندن).
    برای نمایشِ «آهنگ‌های لیست» در منوی کمک/پنل استفاده می‌شود.
    """
    return list(_music_queue.get(chat_id, []))


def push_to_queue(chat_id: int, track: dict) -> int:
    """اضافه کردن یک آهنگ به انتهای صف گروه و برگرداندن موقعیت آن در صف."""
    if chat_id not in _music_queue:
        _music_queue[chat_id] = []
    _music_queue[chat_id].append(track)
    return len(_music_queue[chat_id])


def pop_from_queue(chat_id: int) -> dict:
    """برداشتن اولین آهنگ از ابتدای صف (FIFO). در صورت خالی بودن، دیکشنری خالی برمی‌گرداند."""
    if chat_id in _music_queue and _music_queue[chat_id]:
        return _music_queue[chat_id].pop(0)
    return {}


def clear_queue(chat_id: int):
    """خالی کردن کامل صف آهنگ‌های گروه."""
    if chat_id in _music_queue:
        _music_queue[chat_id] = []