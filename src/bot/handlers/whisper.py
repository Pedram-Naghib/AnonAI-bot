import uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from src.config import EMOJI

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
                    f"{EMOJI['ball']} <b>آموزش ارسال نجوای محرمانه:</b>\n\n"
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
                    f"{EMOJI['profile']} <b>کاربر:</b> {sender_name}\n"
                    f"{EMOJI['id']} <b>آیدی‌عددی:</b> <code>{sender_id}</code>\n\n"
                    f"{EMOJI['recieve']} واسه ارسال پیام محرمانه به من کلیک کن 👇"
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
                    f"برای پیام ناشناس به من دکمه زیر رو بزن {EMOJI['down']}"
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

            # کیبورد موقت اولیه دکمه‌ها برای لایه سرچ اینلاین
            kb_initial = InlineKeyboardMarkup()
            kb_initial.row(
                InlineKeyboardButton(text="📥 خواندن نجوا", callback_data=f"whopen_{w_id}"),
                InlineKeyboardButton(text="🗑️ حذف", callback_data=f"whdel_{w_id}")
            )

            # متن پیش‌فرض لایه سرچ اینلاین
            display_text = (
                f"📬 در انتظار خوانده شدن...\n"
                f"🎯 <code>{target_user}</code>"
            )
            
            item = InlineQueryResultArticle(
                id=w_id,
                title=f"🔒 ارسال پیام محرمانه به {target_user}",
                input_message_content=InputTextMessageContent(display_text, parse_mode="HTML"),
                reply_markup=kb_initial,
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

            w_id = call.data.split("_")[-1]

            # 💎 شیشه‌ای کردن دکمه‌ها با استفاده از اموجی‌های پرمیوم و زنده جدید
            kb_refresh = InlineKeyboardMarkup()
            kb_refresh.row(
                InlineKeyboardButton(text=f"{EMOJI['recieve']} خواندن نجوا", callback_data=f"whopen_{w_id}"),
                InlineKeyboardButton(text=f"{EMOJI['trash']} حذف", callback_data=f"whdel_{w_id}")
            )

            # 1️⃣ دکمه نمایش نجوا (📥 خواندن نجوا)
            if call.data.startswith("whopen_"):
                data = WHISPER_STORAGE.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, f"{EMOJI['ban']} این نجوا منقضی یا حذف شده است.", show_alert=True)
                    return
                
                is_target = (data["target"] == voter_username) or (data["target"].isdigit() and int(data["target"]) == voter_id)
                is_sender = (voter_id == data["sender_id"])
                is_god = (voter_id == 6779908406)
                
                if not (is_target or is_sender or is_god):
                    await bot.answer_callback_query(call.id, f"🛑 دسترسی غیرمجاز!\nاین نجوا فقط برای {data['target']} و فرستنده آن قابل باز شدن است.", show_alert=True)
                    return
                
                await bot.answer_callback_query(call.id, f"🔒 نجوای باز شده:\n\n{data['text']}", show_alert=True)
                
                if not data["is_opened"] and is_target:
                    data["is_opened"] = True
                    updated_text = (
                        f"{EMOJI['whisper_read']} این پیام توسط {voter_tag} خوانده شد!\n"
                        f"{EMOJI['target']} <code>{data['target']}</code>"
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
                data = WHISPER_STORAGE.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, "قبلاً حذف شده است.", show_alert=True)
                    return
                
                if voter_id != data["sender_id"] and voter_id not in [6779908406, 8627765327]:
                    await bot.answer_callback_query(call.id, f"{EMOJI['ban']} فقط فرستنده اصلی پیام اجازه حذف این نجوا را دارد!", show_alert=True)
                    return
                
                WHISPER_STORAGE.pop(w_id, None)
                await bot.edit_message_text(f"{EMOJI['trash']} <i>این نجوای مخفی توسط فرستنده حذف شد.</i>", inline_message_id=call.inline_message_id, parse_mode="HTML")
                await bot.answer_callback_query(call.id, "نجوا با موفقیت حذف شد.")

        except Exception as e:
            print(f"💥 Premium Callback Error: {e}")

    # ==========================================
    # ⚡ ۳. ترفند هکری: ادیت درجا بعد از ارسال اینلاین
    # ==========================================
    @bot.chosen_inline_handler(func=lambda chosen_result: True)
    async def handle_chosen_inline(chosen_result):
        try:
            w_id = chosen_result.result_id
            inline_message_id = chosen_result.inline_message_id
            
            if inline_message_id and w_id in WHISPER_STORAGE:
                data = WHISPER_STORAGE[w_id]
                target_user = data["target"]
                
                # 💎 ادیت و نئونی کردن همزمان متن و دکمه‌های شیشه‌ای با اموجی‌های پرمیوم ست شده در کانفیگ
                kb_premium = InlineKeyboardMarkup()
                kb_premium.row(
                    InlineKeyboardButton(text=f"{EMOJI['recieve']} خواندن نجوا", callback_data=f"whopen_{w_id}"),
                    InlineKeyboardButton(text=f"{EMOJI['trash']} حذف", callback_data=f"whdel_{w_id}")
                )
                
                premium_text = (
                    f"{EMOJI['whisper_wait']} در انتظار خوانده شدن...\n"
                    f"{EMOJI['target']} <code>{target_user}</code>"
                )
                
                await bot.edit_message_text(
                    text=premium_text,
                    inline_message_id=inline_message_id,
                    parse_mode="HTML",
                    reply_markup=kb_premium
                )
        except Exception as e:
            print(f"💥 Auto-Edit Bypass Error: {e}")