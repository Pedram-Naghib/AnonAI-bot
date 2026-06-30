"""
دستورِ «کمک» — منوی راهنمای امکاناتِ ربات در گروه (با دکمه‌های شیشه‌ای).

به‌جای فرستادنِ یک پیامِ طولانی، یک پیامِ کوتاهِ معرفی + ۳ دکمهٔ بخش
(پیامِ ناشناس / نجوا / موزیک) + دکمهٔ «بستن» نشان داده می‌شود. با زدنِ هر
دکمه، همون پیام (نه پیامِ جدید) با متنِ همون بخش و یک دکمهٔ «بازگشت»
ویرایش می‌شود تا چت شلوغ نشه. دکمهٔ «بستن» در همهٔ حالت‌ها پیام را پاک می‌کند.
"""

from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from src.config import EMOJI


# ── متنِ معرفیِ کوتاه (صفحهٔ اول) ──────────────────────────
def _build_intro_text() -> str:
    return (
        f"{EMOJI['light']['html']} <b>راهنمای ربات</b>\n\n"
        "یکی از بخش‌های زیر رو انتخاب کن تا توضیحاتش رو ببینی:"
    )


def _intro_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton(f"{EMOJI['mail']['char']} پیامِ ناشناس", callback_data="help_anon"))
    kb.row(InlineKeyboardButton(f"{EMOJI['lock']['char']} نجوا", callback_data="help_whisper"))
    kb.row(InlineKeyboardButton(f"{EMOJI['fire']['char']} موزیک و ویدیو", callback_data="help_music"))
    kb.row(InlineKeyboardButton(f"{EMOJI['crcl_no']['char']} بستن", callback_data="help_close", style="danger"))
    return kb


# ── متنِ هر بخش + دکمهٔ بازگشت/بستن ─────────────────────────
def _back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton(f"{EMOJI['left']['char']} بازگشت", callback_data="help_back"))
    kb.row(InlineKeyboardButton(f"{EMOJI['crcl_no']['char']} بستن", callback_data="help_close", style="danger"))
    return kb


def _build_anon_text() -> str:
    return (
        f"{EMOJI['mail']['html']} <b>پیامِ ناشناس</b>\n\n"
        f"به {EMOJI['bot']['char']} پیوی بده و دکمهٔ «ارسال پیام ناشناس به آیدی خاص» رو بزن، "
        "یا لینکِ اختصاصیِ خودت رو (از همون منو) به بقیه بده تا برات پیامِ ناشناس بفرستن. "
        "می‌تونی به پیام‌های دریافتی هم ناشناس جواب بدی."
    )


def _build_whisper_text(bot_username: str) -> str:
    return (
        f"{EMOJI['lock']['html']} <b>نجوای اینلاین (توی همین گروه)</b>\n\n"
        f"توی هر چتی بنویس:\n<code>@{bot_username} متنِ نجوا</code>\n"
        "بعد از خط بعدی، آیدی عددی یا یوزرنیمِ گیرنده رو بنویس. مثال:\n"
        f"<code>@{bot_username} سلام چطوری؟\n123456789</code>\n\n"
        "یک پیامِ «در انتظار خوانده شدن» توی گروه می‌فرستی که فقط گیرنده "
        "(یا خودِ تو) می‌تونه با زدنِ دکمهٔ «خواندن نجوا» بازش کنه — بقیه فقط "
        "می‌بینن که نجوایی فرستاده شده، نه متنش رو."
    )


def _build_music_text() -> str:
    return (
        f"{EMOJI['fire']['html']} <b>موزیک و ویدیو در ویس‌چت</b>\n\n"
        "روی یک فایلِ صوتی، ویس، ویدیو یا پیامِ ویدیویی ریپلای کن و بنویس:\n"
        "<code>پخش</code>\n\n"
        "<u>کنترلِ پخش (فقط برای کسی که پخش رو شروع کرده یا ادمین‌ها):</u>\n"
        "• <code>بعدی</code> — رفتن سراغِ آهنگِ بعدیِ صف\n"
        "• <code>پایان پخش</code> — توقفِ کامل و خروج از ویس‌چت\n"
        "• <code>هاب</code> — نمایشِ دوبارهٔ هابِ کنترل با دکمه‌های شیشه‌ای\n\n"
        "نکته: قبل از «پخش»، باید خودِ ویس‌چتِ گروه از قبل باز باشه."
    )


def register_help_handlers(bot: AsyncTeleBot):

    # ── دستورِ «کمک»: نمایشِ منوی معرفی ────────────────────
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
            await bot.reply_to(
                message,
                _build_intro_text(),
                parse_mode="HTML",
                reply_markup=_intro_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception as e:
            print(f"💥 /کمک error: {e}")

    # ── کال‌بکِ دکمه‌های منوی کمک ───────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("help_"))
    async def handle_help_buttons(call):
        action = call.data.split("help_")[-1]  # anon | whisper | music | back | close

        try:
            if action == "close":
                try:
                    await bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception as e:
                    print(f"⚠️ Failed to delete help message: {e}")
                    await bot.answer_callback_query(call.id, "⚠️ حذفِ پیام ممکن نشد.", show_alert=True)
                    return
                return

            if action == "back":
                await bot.edit_message_text(
                    _build_intro_text(),
                    call.message.chat.id, call.message.message_id,
                    parse_mode="HTML", reply_markup=_intro_keyboard(),
                )
                await bot.answer_callback_query(call.id)
                return

            if action == "anon":
                text = _build_anon_text()
            elif action == "whisper":
                bot_info = await bot.get_me()
                text = _build_whisper_text(bot_info.username)
            elif action == "music":
                text = _build_music_text()
            else:
                await bot.answer_callback_query(call.id)
                return

            await bot.edit_message_text(
                text, call.message.chat.id, call.message.message_id,
                parse_mode="HTML", reply_markup=_back_keyboard(),
            )
            await bot.answer_callback_query(call.id)
        except Exception as e:
            print(f"💥 help button error: {e}")