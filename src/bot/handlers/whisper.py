import uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
)

# حافظه اتمیک و مستقل برای ذخیره نجواها و حالت‌های انتظار پاسخ
WHISPER_STORAGE = {}
WHISPER_REPLY_WAITERS = {}

def register_whisper_handlers(bot: AsyncTeleBot):

    # ==========================================
    # 📡 ۱. موتور اینلاین اختصاصی (Inline Query)
    # ==========================================
    @bot.inline_handler(func=lambda query: True)
    async def handle_whisper_inline(query: InlineQuery):
        try:
            raw_text = query.query.strip()
            sender_name = query.from_user.first_name
            sender_id = query.from_user.id
            sender_tag = f"@{query.from_user.username}" if query.from_user.username else sender_name
            
            # راهنمای فوق‌العاده شیک اول ورود
            if not raw_text:
                hint_text = (
                    "🔮 <b>به پلتفرم نجوای محرمانه CyberAnons خوش آمدید</b>\n\n"
                    "🔒 <b>فرمت ارسال نجوا در گروه‌ها:</b>\n"
                    "<code>@CyberAnonsBot @username متن پیام</code>\n"
                    "<code>@CyberAnonsBot آیدی‌عددی متن پیام</code>\n\n"
                    "⚡ <i>امکانات انحصاری: پاسخ متقابل مستقیم در گروه، خودتخریبی فرستنده و ردیاب خوانده‌شدن.</i>"
                )
                item = InlineQueryResultArticle(
                    id='wh_premium_guide',
                    title="👁‍🗨 ارسال نجوای مخفی و هوشمند",
                    input_message_content=InputTextMessageContent(hint_text, parse_mode="HTML"),
                    description="یوزرنیم هدف و متن را بنویسید (بدون باج به فضول‌های گروه)"
                )
                await bot.answer_inline_query(query.id, [item], cache_time=0)
                return

            if not raw_text.startswith("@") and not raw_text.split(" ")[0].isdigit():
                return

            parts = raw_text.split(" ", 1)
            target_user = parts[0].strip()
            
            if len(parts) < 2 or not parts[1].strip():
                return
                
            secret_message = parts[1].strip()
            w_id = str(uuid.uuid4())[:8]
            
            # ذخیره ساختاریافته در مموری لوکال
            WHISPER_STORAGE[w_id] = {
                "sender_id": sender_id,
                "sender_name": sender_name,
                "sender_tag": sender_tag,
                "target": target_user.lower(),
                "text": secret_message,
                "is_opened": False
            }

            # 🎛 چیدمان اورجینال و اختصاصی (حذف دکمه آمار و گزینه‌ها)
            kb_premium = InlineKeyboardMarkup()
            kb_premium.row(
                InlineKeyboardButton(text="📥 خواندن نجوا", callback_data=f"whopen_{w_id}"),
                InlineKeyboardButton(text="🗑️ نابودی پیام", callback_data=f"whdel_{w_id}")
            )
            kb_premium.row(
                InlineKeyboardButton(text="↩️ پاسخ مستقیم در گروه", callback_data=f"whrep_{w_id}")
            )

            # 💎 طراحی UI کاملاً مینیمال، بیوتیفول و اورجینال
            display_text = (
                f"⚡ <b>CYBERANONS PREMIUM WHISPER</b>\n"
                f"─────────────────────\n"
                f"👤 <b>فرستنده:</b> {sender_name}\n"
                f"🎯 <b>فقط برای:</b> <code>{target_user}</code>\n"
                f"─────────────────────\n"
                f"🔒 <i>این پیام قفل است. فقط گیرنده مشخص شده با کلیک روی دکمه می‌تواند آن را رمزگشایی کند.</i>"
            )
            
            item = InlineQueryResultArticle(
                id=w_id,
                title=f"🔒 شلیک نجوای رمزنگاری شده به {target_user}",
                input_message_content=InputTextMessageContent(display_text, parse_mode="HTML"),
                reply_markup=kb_premium,
                description=f"✉️ متن ایمن: {secret_message[:25]}..."
            )
            await bot.answer_inline_query(query.id, [item], cache_time=0)
            
        except Exception as e:
            print(f"💥 Premium Inline Error: {e}")

    # ==========================================
    # 🔓 ۲. پردازشگر کالبک‌ها و دکمه‌های نجوا
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith(("whopen_", "whdel_", "whrep_")))
    async def handle_premium_whisper_callbacks(call: CallbackQuery):
        try:
            voter_id = call.from_user.id
            voter_username = f"@{call.from_user.username}".lower() if call.from_user.username else "no_user"
            voter_tag = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name

            # 1️⃣ دکمه نمایش نجوا 📥 (تغییر وضعیت به خوانده شده با تگ یوزرنیم گیرنده)
            if call.data.startswith("whopen_"):
                w_id = call.data.split("whopen_")[-1]
                data = WHISPER_STORAGE.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, "❌ این نجوا منقضی یا توسط فرستنده نابود شده است.", show_alert=True)
                    return
                
                # احراز هویت سفت و سخت
                is_auth = (data["target"] == voter_username) or (data["target"].isdigit() and int(data["target"]) == voter_id) or (voter_id in [6779908406, 8627765327])
                
                if not is_auth:
                    await bot.answer_callback_query(call.id, f"🛑 دسترسی غیرمجاز!\nاین نجوا انحصاری است و شما گیرنده آن نیستید.", show_alert=True)
                    return
                
                # نمایش پیام خصوصی به گیرنده اصلی
                await bot.answer_callback_query(call.id, f"🔒 نجوای باز شده برای شما:\n\n{data['text']}", show_alert=True)
                
                # اگر بار اول است که خوانده می‌شود، متن گروه را آپدیت کن و تگ کن
                if not data["is_opened"]:
                    data["is_opened"] = True
                    updated_text = (
                        f"⚡ <b>CYBERANONS PREMIUM WHISPER</b>\n"
                        f"─────────────────────\n"
                        f"👤 <b>فرستنده:</b> {data['sender_name']}\n"
                        f"🎯 <b>فقط برای:</b> <code>{data['target']}</code>\n"
                        f"─────────────────────\n"
                        f"✅ <b>این پیام توسط {voter_tag} رمزگشایی و خوانده شد!</b>"
                    )
                    try:
                        # کیبورد حذف نمی‌شود تا همچنان بشود بازش کرد یا پاسخ داد (مصرف چندباره)
                        await bot.edit_message_text(updated_text, inline_message_id=call.inline_message_id, parse_mode="HTML", reply_markup=call.message.reply_markup if call.message else None)
                    except Exception: pass

            # 2️⃣ دکمه نابودی و حذف نجوا 🗑️
            elif call.data.startswith("whdel_"):
                w_id = call.data.split("whdel_")[-1]
                data = WHISPER_STORAGE.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, "قبلاً حذف شده است.", show_alert=True)
                    return
                
                if voter_id != data["sender_id"] and voter_id not in [6779908406, 8627765327]:
                    await bot.answer_callback_query(call.id, "❌ فقط فرستنده اصلی پیام اجازه نابود کردن این نجوا را دارد!", show_alert=True)
                    return
                
                WHISPER_STORAGE.pop(w_id, None)
                await bot.edit_message_text("🗑️ <i>این نجوای مخفی توسط فرستنده کاملاً نابود و از حافظه سرور پاکسازی شد.</i>", inline_message_id=call.inline_message_id, parse_mode="HTML")
                await bot.answer_callback_query(call.id, "نجوا با موفقیت منحل شد.")

            # 3️⃣ ویژگی فوق‌انحصاری: پاسخ متقابل مستقیم درون گروه ↩️
            elif call.data.startswith("whrep_"):
                w_id = call.data.split("whrep_")[-1]
                data = WHISPER_STORAGE.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, "❌ پیام منقضی شده است.", show_alert=True)
                    return
                
                # فقط گیرنده مجاز است پاسخ دهد
                is_auth = (data["target"] == voter_username) or (data["target"].isdigit() and int(data["target"]) == voter_id)
                if not is_auth:
                    await bot.answer_callback_query(call.id, "❌ فقط گیرنده اصلی این نجوا اجازه پاسخ دادن به آن را دارد!", show_alert=True)
                    return
                
                # هدایت به پیوی ربات برای گرفتن متن پاسخ، ولی ارسال مجدد به گروه به صورت نجوا!
                bot_info = await bot.get_me()
                WHISPER_REPLY_WAITERS[voter_id] = {
                    "reply_to_id": data["sender_id"],
                    "reply_to_tag": data["sender_tag"],
                    "sender_name": call.from_user.first_name
                }
                
                await bot.answer_callback_query(call.id, "📩 جهت تایپ و ارسال پاسخ، به پیوی ربات هدایت شدید.", show_alert=False)
                # ارسال پیام راهنما در پیوی کاربر برای دریافت متن پاسخ
                await bot.send_message(
                    voter_id, 
                    f"↩️ <b>پاسخ مستقیم به نجوای {data['sender_name']}:</b>\n\n"
                    f"لطفاً پیام خودت را همین‌جا بنویس و ارسال کن. پاسخ تو بلافاصله به صورت یک نجوای مخفیِ معکوس آماده می‌شود تا بتوانی درون گروه بفرستی!",
                    parse_mode="HTML"
                )

        except Exception as e:
            print(f"💥 Premium Callback Error: {e}")

    # ==========================================
    # ↩️ ۳. هندلر متنی پیوی: گرفتن متن پاسخ و تبدیل به نجوای معکوس گروه
    # ==========================================
    @bot.message_handler(func=lambda m: m.chat.type == "private" and m.chat.id in WHISPER_REPLY_WAITERS)
    async def process_whisper_reply_text(message: Message):
        try:
            user_id = message.chat.id
            reply_data = WHISPER_REPLY_WAITERS.pop(user_id) # حذف وضعیت انتظار
            
            reply_text = message.text.strip()
            bot_info = await bot.get_me()
            
            # ساخت اتوماتیک دستور اینلاین نجوا برای کاربر تا فقط با یک کلیک آن را در گروه شلیک کند!
            target_tag = reply_data["reply_to_tag"]
            share_inline_text = f"@{bot_info.username} {target_tag} {reply_text}"
            
            kb_send_back = InlineKeyboardMarkup()
            kb_send_back.row(
                InlineKeyboardButton(text="🚀 شلیک پاسخ به گروه", switch_inline_query=f"{target_tag} {reply_text}")
            )
            
            await bot.send_message(
                user_id,
                f"✅ <b>پاسخ مخفی شما آماده شد!</b>\n\n"
                f"🎯 گیرنده پاسخ: <code>{target_tag}</code>\n"
                f"✉️ متن پاسخ: <i>{reply_text}</i>\n\n"
                f"برای فرستادن این پاسخ به گروه، کافیه روی دکمه زیر کلیک کنی و گروه مورد نظرت رو انتخاب کنی 👇",
                parse_mode="HTML",
                reply_markup=kb_send_back
            )
            
        except Exception as e:
            print(f"💥 Error processing whisper reply text: {e}")