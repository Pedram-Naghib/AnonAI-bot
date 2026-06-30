"""
دستورِ «کمک» — راهنمای کاملِ امکاناتِ ربات در گروه.

این دستور برای همهٔ اعضا (نه فقط ادمین‌ها) در دسترس است و پیامِ ناشناس،
نجوای اینلاین، و سیستمِ موزیکِ ویس‌چت را در یک پیام خلاصه می‌کند.
"""

from telebot.async_telebot import AsyncTeleBot
from src.config import EMOJI


def _build_help_text(bot_username: str) -> str:
    return (
        f"{EMOJI['light']['html']} <b>راهنمای کاملِ ربات</b>\n"
        "───────────────────\n\n"

        f"{EMOJI['mail']['html']} <b>۱) پیامِ ناشناس</b>\n"
        f"به {EMOJI['bot']['char']} پیوی بده و دکمهٔ «ارسال پیام ناشناس به آیدی خاص» رو بزن، "
        "یا لینکِ اختصاصیِ خودت رو (از همون منو) به بقیه بده تا برات پیامِ ناشناس بفرستن. "
        "می‌تونی به پیام‌های دریافتی هم ناشناس جواب بدی.\n\n"

        f"{EMOJI['lock']['html']} <b>۲) نجوای اینلاین (توی همین گروه)</b>\n"
        f"توی هر چتی بنویس:\n<code>@{bot_username} متنِ نجوا</code>\n"
        "بعد از خط بعدی، آیدی عددی یا یوزرنیمِ گیرنده رو بنویس. مثال:\n"
        f"<code>@{bot_username} سلام چطوری؟\n123456789</code>\n"
        "یک پیامِ «در انتظار خوانده شدن» توی گروه می‌فرستی که فقط گیرنده "
        "(یا خودِ تو) می‌تونه با زدنِ دکمهٔ «خواندن نجوا» بازش کنه — بقیه فقط "
        "می‌بینن که نجوایی فرستاده شده، نه متنش رو.\n\n"

        f"{EMOJI['fire']['html']} <b>۳) موزیک و ویدیو در ویس‌چت</b>\n"
        "روی یک فایلِ صوتی، ویس، ویدیو یا پیامِ ویدیویی ریپلای کن و بنویس:\n"
        "<code>پخش</code>\n\n"
        "<u>کنترلِ پخش (فقط برای کسی که پخش رو شروع کرده یا ادمین‌ها):</u>\n"
        "• <code>بعدی</code> — رفتن سراغِ آهنگِ بعدیِ صف\n"
        "• <code>پایان پخش</code> — توقفِ کامل و خروج از ویس‌چت\n"
        "• <code>هاب</code> — نمایشِ دوبارهٔ هابِ کنترل با دکمه‌های شیشه‌ای\n\n"
        "نکته: قبل از «پخش»، باید خودِ ویس‌چتِ گروه از قبل باز باشه.\n\n"

        f"{EMOJI['question']['html']} <b>سؤالِ دیگه‌ای داری؟</b>\n"
        "همینجا بپرس یا با ادمین‌های گروه در تماس باش."
    )


def register_help_handlers(bot: AsyncTeleBot):

    @bot.message_handler(
        func=lambda m: (
            m.chat.type in ("group", "supergroup")
            and m.text is not None
            and m.text.strip() in ("کمک", "/help", "راهنما", "/کمک")
        ),
        content_types=["text"],
    )
    async def handle_help_command(message):
        try:
            bot_info = await bot.get_me()
            await bot.reply_to(
                message,
                _build_help_text(bot_info.username),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            print(f"💥 /کمک error: {e}")