import uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

# حافظه اتمیک و مستقل برای ذخیره نجواها
WHISPER_STORAGE = {}

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
            
            # دریافت آیدی یوزرنیم ربات به صورت داینامیک
            bot_info = await bot.get_me()
            bot_username = f"@{bot_info.username}"
            
            # راهنمای شیک در صورت خالی بودن ورودی
            if not raw_text:
                hint_text = (
                    "🔮 <b>به سیستم نجوای محرمانه CyberAnons خوش آمدید</b>\n\n"
                    "🔒 <b>فرمت ارسال نجوا در گروه‌ها:</b>\n"
                    "<code>@CyberAnonsBot @username متن پیام</code>\n"
                    "<code>@CyberAnonsBot آیدی‌عددی متن پیام</code>"
                )
                item = InlineQueryResultArticle(
                    id='wh_premium_guide',
                    title="👁‍🗨 ارسال نجوای مخفی و هوشمند",
                    input_message_content=InputTextMessageContent(hint_text, parse_mode="HTML"),
                    description="یوزرنیم هدف و متن را بنویسید"
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

            # 🎛 چیدمان دکمه‌ها
            kb_premium = InlineKeyboardMarkup()
            kb_premium.row(
                InlineKeyboardButton(text="📥 خواندن نجوا", callback_data=f"whopen_{w_id}"),
                InlineKeyboardButton(text="🗑️ حذف", callback_data=f"whdel_{w_id}")
            )

            # 💎 چیدمان فوق‌العاده گنگ و اختصاصی طبق ترتیب درخواستی شما:
            # ۱. آیدی ربات | ۲. وضعیت پیام | ۳. آیدی گیرنده
            display_text = (
                f"<b>via {bot_username}</b>\n"
                f"📬 در انتظار خوانده شدن...\n"
                f"🎯 <code>{target_user}</code>"
            )
            
            item = InlineQueryResultArticle(
                id=w_id,
                title=f"🔒 ارسال پیام محرمانه به {target_user}",
                input_message_content=InputTextMessageContent(display_text, parse_mode="HTML"),
                reply_markup=kb_premium,
                description=f"نجوا به {target_user} ارسال شد"
            )
            await bot.answer_inline_query(query.id, [item], cache_time=0)
            
        except Exception as e:
            print(f"💥 Premium Inline Error: {e}")

    # ==========================================
    # 🔓 ۲. پردازشگر کالبک‌ها و دکمه‌های نجوا
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith(("whopen_", "whdel_")))
    async def handle_premium_whisper_callbacks(call: CallbackQuery):
        try:
            voter_id = call.from_user.id
            voter_username = f"@{call.from_user.username}".lower() if call.from_user.username else "no_user"
            voter_tag = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name

            bot_info = await bot.get_me()
            bot_username = f"@{bot_info.username}"

            # 1️⃣ دکمه نمایش نجوا 📥
            if call.data.startswith("whopen_"):
                w_id = call.data.split("whopen_")[-1]
                data = WHISPER_STORAGE.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, "❌ این نجوا منقضی یا حذف شده است.", show_alert=True)
                    return
                
                # بررسی دسترسی فرستنده، گیرنده و ادمین‌ها
                is_auth = (
                    (data["target"] == voter_username) or 
                    (data["target"].isdigit() and int(data["target"]) == voter_id) or 
                    (voter_id == data["sender_id"]) or 
                    (voter_id in [6779908406, 8627765327])
                )
                
                if not is_auth:
                    await bot.answer_callback_query(call.id, f"🛑 دسترسی غیرمجاز!\nاین نجوا فقط برای {data['target']} و فرستنده آن قابل باز شدن است.", show_alert=True)
                    return
                
                # نمایش متن مخفی درون پاپ‌آپ خصوصی تلگرام
                await bot.answer_callback_query(call.id, f"🔒 نجوای باز شده:\n\n{data['text']}", show_alert=True)
                
                # تغییر وضعیت به خوانده شده با حفظ چیدمان درخواستی شما
                if not data["is_opened"]:
                    data["is_opened"] = True
                    updated_text = (
                        f"<b>via {bot_username}</b>\n"
                        f"✅ این پیام توسط {voter_tag} خوانده شد!\n"
                        f"🎯 <code>{data['target']}</code>"
                    )
                    try:
                        # دکمه‌های شیشه‌ای کاملاً پایدار می‌مانند و حذف نمی‌شوند
                        await bot.edit_message_text(
                            text=updated_text, 
                            inline_message_id=call.inline_message_id, 
                            parse_mode="HTML", 
                            reply_markup=call.message.reply_markup if call.message else None
                        )
                    except Exception: pass

            # 2️⃣ دکمه حذف نجوا 🗑️
            elif call.data.startswith("whdel_"):
                w_id = call.data.split("whdel_")[-1]
                data = WHISPER_STORAGE.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, "قبلاً حذف شده است.", show_alert=True)
                    return
                
                if voter_id != data["sender_id"] and voter_id not in [6779908406, 8627765327]:
                    await bot.answer_callback_query(call.id, "❌ فقط فرستنده اصلی پیام اجازه حذف این نجوا را دارد!", show_alert=True)
                    return
                
                WHISPER_STORAGE.pop(w_id, None)
                await bot.edit_message_text("🗑 <i>این نجوای مخفی توسط فرستنده حذف شد.</i>", inline_message_id=call.inline_message_id, parse_mode="HTML")
                await bot.answer_callback_query(call.id, "نجوا با موفقیت حذف شد.")

        except Exception as e:
            print(f"💥 Premium Callback Error: {e}")