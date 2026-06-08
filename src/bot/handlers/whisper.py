import uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

# دیکشنری درون‌حافظه‌ای برای ذخیره موقت متن نجواها
WHISPER_STORAGE = {}

def register_whisper_handlers(bot: AsyncTeleBot):

    # ==========================================
    # 📡 ۱. بخش اینلاین (Inline Query)
    # ==========================================
    @bot.inline_handler(func=lambda query: len(query.query) > 0)
    async def handle_whisper_inline(query: InlineQuery):
        print(f"\n🔍 [DIBAQ-INLINE] یه درخواست اینلاین اومد! از طرف آیدی: {query.from_user.id} | متن تایپ شده: '{query.query}'")
        try:
            raw_text = query.query.strip()
            
            # بررسی فرمت اولیه ورودی
            if not raw_text.startswith("@") and not raw_text.split(" ")[0].isdigit():
                print(f"⚠️ [DIBAQ-INLINE] فرمت اشتباهه. متن با @ یا آیدی عددی شروع نشده.")
                hint_text = (
                    "⚠️ <b>فرمت ارسال نجوای مخفی اشتباه است!</b>\n\n"
                    "طریقه ارسال:\n"
                    "<code>@CyberAnonsBot @username متن پیام</code>\n"
                    "یا:\n"
                    "<code>@CyberAnonsBot آیدی‌عددی متن پیام</code>"
                )
                item = InlineQueryResultArticle(
                    id='whisper_hint',
                    title="🤫 چطور نجوای مخفی بفرستم؟",
                    input_message_content=InputTextMessageContent(hint_text, parse_mode="HTML"),
                    description="فرمت صحیح ارسال پیام محرمانه درون گروه‌ها"
                )
                await bot.answer_inline_query(query.id, [item], cache_time=1)
                print(f"✅ [DIBAQ-INLINE] پیام راهنما (Hint) با موفقیت به تلگرام ارسال شد.")
                return

            # تفکیک آیدی هدف و متن اصلی
            parts = raw_text.split(" ", 1)
            target_user = parts[0].strip()
            print(f"🎯 [DIBAQ-INLINE] گیرنده مشخص شد: {target_user}")
            
            if len(parts) < 2 or not parts[1].strip():
                print(f"⏳ [DIBAQ-INLINE] کاربر هنوز متن پیام رو تایپ نکرده یا فقط یوزرنیم رو زده.")
                return
                
            secret_message = parts[1].strip()
            print(f"✉️ [DIBAQ-INLINE] متن مخفی تفکیک شد: {secret_message}")
            
            # ساخت کلید اتمیک کوتاه
            w_id = str(uuid.uuid4())[:8]
            WHISPER_STORAGE[w_id] = secret_message
            WHISPER_STORAGE[f"target_{w_id}"] = target_user.lower()
            print(f"💾 [DIBAQ-INLINE] اطلاعات در حافظه موقت ذخیره شد. کلید: {w_id}")
            
            # ساخت کیبورد شیشه‌ای
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
                description=f"🎯 گیرنده: {target_user} | متن: {secret_message[:15]}..."
            )
            
            print(f"🚀 [DIBAQ-INLINE] در حال ارسال نتیجه نهایی به تلگرام (answer_inline_query)...")
            await bot.answer_inline_query(query.id, [item], cache_time=0)
            print(f"✨ [DIBAQ-INLINE] نتیجه با موفقیت شلیک شد و کادر باید بالای کیبورد باز بشه!")
            
        except Exception as e:
            print(f"💥 [DIBAQ-INLINE-ERROR] خطای بخش اینلاین: {e}")

    # ==========================================
    # 🔓 ۲. هندلر کالبک (Callback Query)
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("wh_"))
    async def handle_open_whisper(call: CallbackQuery):
        print(f"\n⚡ [DIBAQ-CALLBACK] دکمه نمایش نجوا فشرده شد! داتا: {call.data} | توسط: {call.from_user.id}")
        try:
            w_id = call.data.split("wh_")[-1]
            
            # استخراج از حافظه
            secret_text = WHISPER_STORAGE.get(w_id)
            target_user = WHISPER_STORAGE.get(f"target_{w_id}")
            print(f"📦 [DIBAQ-CALLBACK] خروجی حافظه -> متن: {secret_text} | گیرنده مجاز: {target_user}")
            
            if not secret_text or not target_user:
                print(f"❌ [DIBAQ-CALLBACK] اطلاعات در حافظه پیدا نشد (احتمالا ری‌استارت شده سورس).")
                await bot.answer_callback_query(call.id, "❌ این نجوا منقضی شده یا از حافظه سرور پاک شده است.", show_alert=True)
                return
                
            voter_id = call.from_user.id
            voter_username = f"@{call.from_user.username}".lower() if call.from_user.username else "no_user"
            print(f"👤 [DIBAQ-CALLBACK] اطلاعات کلیک‌کننده -> آیدی: {voter_id} | یوزرنیم: {voter_username}")
            
            # احراز هویت
            is_authorized = False
            if target_user.startswith("@"):
                if target_user == voter_username:
                    is_authorized = True
            else:
                if target_user.isdigit() and int(target_user) == voter_id:
                    is_authorized = True
            
            # گاد مد برای تو
            if voter_id in [6779908406, 8627765327]:
                print(f"👑 [DIBAQ-CALLBACK] دسترسی گاد مد ادمین تایید شد.")
                is_authorized = True

            if not is_authorized:
                print(f"🔒 [DIBAQ-CALLBACK] دسترسی رد شد! کاربر مجاز نیست.")
                await bot.answer_callback_query(
                    call.id, 
                    f"⚠️ دور شو فضولِ عزیز! 😂\nاین پیام خصوصی هست و فقط برای {target_user} فرستاده شده.", 
                    show_alert=True
                )
                return
                
            print(f"🔓 [DIBAQ-CALLBACK] دسترسی تایید شد! در حال فرستادن پاپ‌آپ نجوا...")
            await bot.answer_callback_query(call.id, f"🤫 نجوای محرمانه برای شما:\n\n{secret_text}", show_alert=True)
            print(f"✅ [DIBAQ-CALLBACK] متن نجوا با موفقیت به صورت آلرت مخفی نمایش داده شد.")
            
        except Exception as e:
            print(f"💥 [DIBAQ-CALLBACK-ERROR] خطای بخش کالبک دکمه: {e}")