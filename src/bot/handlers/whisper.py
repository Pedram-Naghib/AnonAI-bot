import uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

# یک دیکشنری درون‌حافظه‌ای (In-Memory) برای ذخیره موقت متن نجواها بدون درگیر کردن دیتابیس
# کلید: یک کد تصادفی کوتاه، مقدار: متن پیام نجوا
WHISPER_STORAGE = {}

def register_whisper_handlers(bot: AsyncTeleBot):

    # ==========================================
    # 📡 ۱. بخش اینلاین (Inline Query): گوش به زنگ زدن آیدی ربات در گروه‌ها
    # ==========================================
    @bot.inline_handler(func=lambda query: len(query.query) > 0)
    async def handle_whisper_inline(query: InlineQuery):
        try:
            raw_text = query.query.strip()
            
            # فرمت ارسالی باید اینطوری باشه: @username متن پیام
            # یا: user_id متن پیام
            if not raw_text.startswith("@") and not raw_text.split(" ")[0].isdigit():
                # راهنمای استفاده برای کاربر اگر فرمت را اشتباه زد
                hint_content = InputTextMessageContent(
                    "⚠️ <b>فرمت ارسال نجوای مخفی:</b>\n\n"
                    "<code>@CyberAnonsBot @username متن پیام</code>\n"
                    "یا اگر یوزرنیم ندارد:\n"
                    "<code>@CyberAnonsBot آیدی‌عددی متن پیام</code>",
                    parse_mode="HTML"
                )
                item = InlineQueryResultArticle(
                    id='whisper_hint',
                    title="🤫 چطور نجوای مخفی بفرستم؟",
                    input_message_content=hint_content,
                    description="فرمت صحیح ارسال پیام محرمانه درون گروه‌ها"
                )
                await bot.answer_inline_query(query.id, [item], cache_time=1)
                return

            # تفکیک آیدی پارتنر هدف و متن اصلی پیام
            parts = raw_text.split(" ", 1)
            target_user = parts[0] # می‌تواند @username یا ID عددی باشد
            
            if len(parts) < 2 or not parts[1].strip():
                return # هنوز متن پیام را ننوشته است
                
            secret_message = parts[1].strip()
            
            # ساخت یک کلید اختصاصی و اتمیک برای این پیام
            w_id = str(uuid.uuid4())[:8]
            WHISPER_STORAGE[w_id] = secret_message
            
            # ساخت کیبورد شیشه‌ای نجوا درون گروه
            kb_whisper = InlineKeyboardMarkup()
            kb_whisper.row(
                InlineKeyboardButton(f"👁‍🗨 نمایش نجوای {query.from_user.first_name}", callback_data=f"wh_open_{w_id}_{target_user}")
            )
            
            # متنی که درون گروه برای همه نمایش داده می‌شود
            display_text = (
                f"🤫 <b>یک نجوای مخفی از طرف 👤 {query.from_user.first_name} فرستاده شد!</b>\n"
                f"🔒 این پیام فقط برای <b>{target_user}</b> قابل نمایش است."
            )
            
            result_msg = InputTextMessageContent(display_text, parse_mode="HTML")
            
            # آرتیکل اصلی که در منوی پاپ‌آپ تلگرام به کاربر نشان داده می‌شود تا رویش کلیک کند
            item = InlineQueryResultArticle(
                id=w_id,
                title=f"🔒 ارسال نجوای محرمانه به {target_user}",
                input_message_content=result_msg,
                reply_markup=kb_whisper,
                description=f"✉️ متن مخفی: {secret_message[:20]}..."
            )
            
            await bot.answer_inline_query(query.id, [item], cache_time=0)
            
        except Exception as e:
            print(f"💥 Inline Whisper Error: {e}")

    # ==========================================
    # 🔓 ۲. هندلر کالبک: پردازش دکمهٔ «نمایش نجوا» توسط کاربران گروه
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("wh_open_"))
    async def handle_open_whisper(call: CallbackQuery):
        try:
            # کالبک دیتا شامل: wh_open_[w_id]_[target_user]
            data_parts = call.data.split("_")
            w_id = data_parts[2]
            target_user = data_parts[3] # می‌تواند @username یا ID عددی باشد
            
            voter_id = call.from_user.id
            voter_username = f"@{call.from_user.username}".lower() if call.from_user.username else "no_user"
            
            # بررسی اینکه آیا کلیک‌کننده همان کاربر مجاز است یا خیر
            is_authorized = False
            
            if target_user.startswith("@"):
                if target_user.lower() == voter_username:
                    is_authorized = True
            else:
                if target_user.isdigit() and int(target_user) == voter_id:
                    is_authorized = True
                    
            # 🛑 پاتک امنیتی: ادمین‌های ارشد ربات (God Mode) همیشه اجازه دیدن دارند (اختیاری)
            if voter_id in [6779908406, 8627765327]:
                is_authorized = True

            if not is_authorized:
                # اگر فضول‌های گروه روی دکمه کلیک کنند، این ارور را به صورت پاپ‌آپ (Alert) می‌بینند:
                await bot.answer_callback_query(
                    call.id, 
                    f"⚠️ دور شو فضولِ عزیز! 😂\nاین پیام خصوصی هست و فقط برای {target_user} فرستاده شده.", 
                    show_alert=True
                )
                return
                
            # اگر کاربر مجاز بود، متن اصلی را از حافظه می‌خوانیم
            secret_text = WHISPER_STORAGE.get(w_id)
            
            if not secret_text:
                await bot.answer_callback_query(call.id, "❌ این نجوا منقضی شده یا از روی حافظه سرور رندر پاک شده است.", show_alert=True)
                return
                
            # نشان دادن متن مخفی به صورت پاپ‌آپ اختصاصی فقط و فقط برای همان کاربر مجاز! 🔥
            await bot.answer_callback_query(call.id, f"🤫 نجوای محرمانه برای شما:\n\n{secret_text}", show_alert=True)
            
        except Exception as e:
            print(f"💥 Error opening whisper: {e}")