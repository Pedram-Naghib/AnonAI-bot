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
            
            # 💎 منوی چندگزینه‌ای اختصاصی (وقتی ورودی خالی است)
            if not raw_text:
                items = []
                
                # گزینه‌ی ۱: آموزش ارسال نجوا
                guide_text = (
                    "🔮 <b>آموزش ارسال نجوای محرمانه:</b>\n\n"
                    "ابتدا متن نجوا رو بنویس و در خط بعد آیدی گیرنده رو قرار بده\n\n"
                    "مثال:\n"
                    f"<code>{bot_username} سلام چطوری؟\n{sender_id}</code>"
                )
                items.append(
                    InlineQueryResultArticle(
                        id='wh_menu_guide',
                        title="💡 آموزش ارسال نجوا",
                        description="ابتدا متن سپس آیدی گیرنده را بنویسید",
                        input_message_content=InputTextMessageContent(guide_text, parse_mode="HTML"),
                        thumbnail_url="https://img.icons8.com/sci-fi/48/question-mark.png"
                    )
                )
                
                # گزینه‌ی ۲: باکس درخواست نجوای اختصاصی
                kb_req_whisper = InlineKeyboardMarkup()
                kb_req_whisper.row(
                    InlineKeyboardButton(
                        text=f"📬 ارسال نجوای خصوصی به {sender_name}", 
                        switch_inline_query_current_chat=f"متن نجوا\n{sender_id}"
                    )
                )
                
                req_whisper_text = (
                    f"👤 <b>کاربر:</b> {sender_name}\n"
                    f"🆔 <b>آیدی‌عددی:</b> <code>{sender_id}</code>\n\n"
                    f"📥 واسه ارسال پیام محرمانه به من کلیک کن 👇"
                )
                items.append(
                    InlineQueryResultArticle(
                        id='wh_menu_request_box',
                        title="🔒 درخواست ارسال پیام محرمانه به من",
                        description="باکس دریافت نجوای مستقیم درون گروه‌ها 🕶️",
                        input_message_content=InputTextMessageContent(req_whisper_text, parse_mode="HTML"),
                        reply_markup=kb_req_whisper,
                        thumbnail_url="https://img.icons8.com/sci-fi/48/speech-bubble-with-dots.png"
                    )
                )
                
                # گزینه‌ی ۳: لینک اختصاصی پیام ناشناس شیشه‌ای
                kb_anon_link = InlineKeyboardMarkup()
                kb_anon_link.row(
                    InlineKeyboardButton(
                        text="💌 ارسال پیام ناشناس", 
                        url=f"https://t.me/{bot_info.username}?start=anon_{sender_id}"
                    )
                )
                
                anon_req_text = (
                    f"برای پیام ناشناس به من دکمه زیر رو بزن 👇"
                )
                items.append(
                    InlineQueryResultArticle(
                        id='wh_menu_anon',
                        title="📥 لینک ناشناس اختصاصی",
                        description="دریافت پیام ناشناس در گروه‌ها و کانال‌ها 🚀",
                        input_message_content=InputTextMessageContent(anon_req_text, parse_mode="HTML"),
                        reply_markup=kb_anon_link,
                        thumbnail_url="https://img.icons8.com/sci-fi/48/fraud.png"
                    )
                )
                
                await bot.answer_inline_query(query.id, items, cache_time=0)
                return

            # ==========================================
            # 🛠️ موتور هوشمند تفکیک ۳ بخشی (متن نجوا + آیدی گیرنده)
            # ==========================================
            lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
            
            if len(lines) >= 2:
                target_user = lines[-1]
                secret_message = "\n".join(lines[:-1])
            else:
                parts = raw_text.rsplit(" ", 1)
                if len(parts) < 2:
                    return
                secret_message = parts[0].strip()
                target_user = parts[1].strip()

            if not target_user.startswith("@") and not target_user.isdigit():
                return

            w_id = str(uuid.uuid4())[:8]
            
            WHISPER_STORAGE[w_id] = {
                "sender_id": sender_id,
                "sender_name": sender_name,
                "sender_tag": sender_tag,
                "target": target_user.lower(),
                "text": secret_message,
                "is_opened": False
            }

            kb_premium = InlineKeyboardMarkup()
            kb_premium.row(
                InlineKeyboardButton(text="📥 خواندن نجوا", callback_data=f"whopen_{w_id}"),
                InlineKeyboardButton(text="🗑️ حذف", callback_data=f"whdel_{w_id}")
            )

            display_text = (
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

            kb_refresh = InlineKeyboardMarkup()
            kb_refresh.row(
                InlineKeyboardButton(text="📥 خواندن نجوا", callback_data=f"{call.data}"),
                InlineKeyboardButton(text="🗑️ حذف", callback_data=f"whdel_{call.data.split('_')[-1]}")
            )

            # 1️⃣ دکمه نمایش نجوا (📥 خواندن نجوا)
            if call.data.startswith("whopen_"):
                w_id = call.data.split("whopen_")[-1]
                data = WHISPER_STORAGE.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, "❌ این نجوا منقضی یا حذف شده است.", show_alert=True)
                    return
                
                # تفکیک دقیق هویت گیرنده واقعی
                is_target = (data["target"] == voter_username) or (data["target"].isdigit() and int(data["target"]) == voter_id)
                is_sender = (voter_id == data["sender_id"])
                is_admin = (voter_id in [6779908406, 8627765327])
                
                # بررسی کلی دسترسی برای خواندن پیام
                if not (is_target or is_sender or is_admin):
                    await bot.answer_callback_query(call.id, f"🛑 دسترسی غیرمجاز!\nاین نجوا فقط برای {data['target']} و فرستنده آن قابل باز شدن است.", show_alert=True)
                    return
                
                # نمایش متن نجوا در پاپ‌آپ برای فرستنده، گیرنده و ادمین
                await bot.answer_callback_query(call.id, f"🔒 نجوای باز شده:\n\n{data['text']}", show_alert=True)
                
                # 🔥 تفکیک ادیت متن: فقط در صورتی که گیرنده (یا ادمین) پیام را باز کند و پیام قبلاً باز نشده باشد
                if not data["is_opened"] and (is_target or is_admin):
                    data["is_opened"] = True
                    updated_text = (
                        f"✅ این پیام توسط {voter_tag} خوانده شد!\n"
                        f"🎯 <code>{data['target']}</code>"
                    )
                    try:
                        await bot.edit_message_text(
                            text=updated_text, 
                            inline_message_id=call.inline_message_id, 
                            parse_mode="HTML", 
                            reply_markup=kb_refresh
                        )
                    except Exception as e:
                        print(f"⚠️ Edit fail ignored: {e}")

            # 2️⃣ دکمه حذف نجوا (🗑️ حذف)
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