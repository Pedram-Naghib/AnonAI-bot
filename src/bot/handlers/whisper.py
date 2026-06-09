import uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

# دیکشنری درون‌حافظه‌ای برای ذخیره موقت متن نجواها بدون درگیر کردن دیتابیس
WHISPER_STORAGE = {}

def register_whisper_handlers(bot: AsyncTeleBot):

    # ==========================================
    # 📡 ۱. بخش اینلاین (Inline Query)
    # ==========================================
    @bot.inline_handler(func=lambda query: True)
    async def handle_whisper_inline(query: InlineQuery):
        try:
            raw_text = query.query.strip()
            
            # اگر کاربر هنوز چیزی تایپ نکرده است، راهنما نشان داده شود
            if not raw_text:
                hint_text = (
                    "🤫 <b>به سیستم نجوای مخفی خوش آمدید!</b>\n\n"
                    "برای ارسال پیام محرمانه درون گروه‌ها، طبق فرمت زیر عمل کنید:\n"
                    "<code>@CyberAnonsBot @username متن پیام</code>\n\n"
                    "🔹 اگر کاربر هدف یوزرنیم ندارد، به جای آن از آیدی عددی استفاده کنید:\n"
                    "<code>@CyberAnonsBot آیدی‌عددی متن پیام</code>"
                )
                item = InlineQueryResultArticle(
                    id='whisper_empty_hint',
                    title="🤫 شروع ارسال نجوای مخفی",
                    input_message_content=InputTextMessageContent(hint_text, parse_mode="HTML"),
                    description="یوزرنیم یا آیدی هدف را به همراه متن پیام بنویسید."
                )
                await bot.answer_inline_query(query.id, [item], cache_time=0)
                return

            # بررسی فرمت صحیح ورودی (شروع با @ یا آیدی عددی)
            if not raw_text.startswith("@") and not raw_text.split(" ")[0].isdigit():
                hint_text = (
                    "⚠️ <b>فرمت ارسال نجوای مخفی اشتباه است!</b>\n\n"
                    "طریقه ارسال صحیح:\n"
                    "<code>@CyberAnonsBot @username متن پیام</code>"
                )
                item = InlineQueryResultArticle(
                    id='whisper_hint',
                    title="⚠️ فرمت اشتباه است!",
                    input_message_content=InputTextMessageContent(hint_text, parse_mode="HTML"),
                    description="پیام باید با @username یا آیدی عددی شروع شود."
                )
                await bot.answer_inline_query(query.id, [item], cache_time=0)
                return

            # تفکیک آیدی هدف و متن اصلی پیام
            parts = raw_text.split(" ", 1)
            target_user = parts[0].strip()
            
            if len(parts) < 2 or not parts[1].strip():
                return  # کاربر هنوز متن پیام را ننوشته است
                
            secret_message = parts[1].strip()
            
            # ساخت کلید اتمیک کوتاه برای ذخیره‌سازی موقت در حافظه
            w_id = str(uuid.uuid4())[:8]
            WHISPER_STORAGE[w_id] = secret_message
            WHISPER_STORAGE[f"target_{w_id}"] = target_user.lower()
            
            # ساخت کیبورد شیشه‌ای نئونی درون گروه
            kb_whisper = InlineKeyboardMarkup()
            kb_whisper.row(
                InlineKeyboardButton(
                    text=f"👁‍🗨 نمایش نجوای {query.from_user.first_name}", 
                    callback_data=f"wh_{w_id}"
                )
            )
            
            display_text = (
                f"🤫 <b>یک نجوای مخفی از طرف 👤 {query.from_user.first_name} فرستاده شد!</b>\n"
                f"🔒 این پیام فقط برای <b>{target_user}</b> قابل نمایش است."
            )
            
            item = InlineQueryResultArticle(
                id=w_id,
                title=f"🔒 ارسال نجوای محرمانه به {target_user}",
                input_message_content=InputTextMessageContent(display_text, parse_mode="HTML"),
                reply_markup=kb_whisper,
                description=f"🎯 گیرنده: {target_user}"
            )
            
            await bot.answer_inline_query(query.id, [item], cache_time=0)
            
        except Exception as e:
            print(f"💥 [Whisper Inline Error]: {e}")

    # ==========================================
    # 🔓 ۲. هندلر کالبک دکمه (Callback Query)
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("wh_"))
    async def handle_open_whisper(call: CallbackQuery):
        try:
            w_id = call.data.split("wh_")[-1]
            
            # استخراج متن پیام و گیرنده مجاز از حافظه
            secret_text = WHISPER_STORAGE.get(w_id)
            target_user = WHISPER_STORAGE.get(f"target_{w_id}")
            
            if not secret_text or not target_user:
                await bot.answer_callback_query(call.id, "❌ این نجوا منقضی شده یا سرور ری‌استارت شده است.", show_alert=True)
                return
                
            voter_id = call.from_user.id
            voter_username = f"@{call.from_user.username}".lower() if call.from_user.username else "no_user"
            
            # بررسی احراز هویت کلیک‌کننده
            is_authorized = False
            if target_user.startswith("@"):
                if target_user == voter_username:
                    is_authorized = True
            else:
                if target_user.isdigit() and int(target_user) == voter_id:
                    is_authorized = True
            
            # دسترسی ادمین ارشد (God Mode)
            if voter_id in [6779908406, 8627765327]:
                is_authorized = True

            if not is_authorized:
                await bot.answer_callback_query(
                    call.id, 
                    f"⚠️ دور شو فضولِ عزیز! 😂\nاین پیام خصوصی هست و فقط برای {target_user} فرستاده شده.", 
                    show_alert=True
                )
                return
                
            # نمایش پیام مخفی به صورت پاپ‌آپ اختصاصی
            await bot.answer_callback_query(call.id, f"🤫 نجوای محرمانه برای شما:\n\n{secret_text}", show_alert=True)
            
        except Exception as e:
            print(f"💥 [Whisper Callback Error]: {e}")