import re
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from src.utils.crypto import encode_user_id, decode_user_id
from src.database.db_manager import (
    register_or_update_user, get_user_state, set_user_state, clear_user_state,
    save_message_mapping, get_anon_sender_by_msg,
    block_user, is_user_blocked, get_super_user_by_msg, get_user_profile_stats
)

GOD_ID = 6779908406

def register_private_anon_handlers(bot: AsyncTeleBot):

    @bot.message_handler(commands=['start'])
    async def handle_start(message):
        if message.chat.type != "private": return
        bot_info = await bot.get_me()
        command_args = message.text.split()
        user_id = message.chat.id
        
        await register_or_update_user(user_id, message.from_user.first_name, message.from_user.username)
        
        main_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        main_keyboard.add(KeyboardButton("📊 آمار من"))
        
        if len(command_args) > 1:
            target_owner_id_encoded = command_args[1]
            target_owner_id = decode_user_id(target_owner_id_encoded)
            
            if target_owner_id and user_id != target_owner_id:
                if await is_user_blocked(owner_id=target_owner_id, blocked_id=user_id):
                    await bot.reply_to(message, "❌ شما توسط این کاربر بلاک شده‌اید.", reply_markup=main_keyboard)
                    return
                await set_user_state(user_id, f"sending_anon_to_{target_owner_id_encoded}")
                await bot.reply_to(message, "📥 در حال ارسال پیام ناشناس... مدیا یا متن خود را بفرستید:", reply_markup=main_keyboard)
                return
        
        secret_code = encode_user_id(user_id)
        anon_link = f"https://t.me/{bot_info.username}?start={secret_code}"
        
        god_text = f"سلام و درود ارباب فاطمه. 🙇‍♂️\nهوش مصنوعی گوش به فرمان شماست.\n\n👁️‍🗨️ <b>دسترسی ارشد ویژه:</b>\nشما برخلاف کاربران عادی، توانایی مشاهدهٔ اطلاعات دقیق فرستندهٔ پیام‌ها را دارید.\n\n🔗 <b>لینک ناشناس ارباب:</b>\n{anon_link}"
        normal_text = f"👋 به ربات پیام ناشناس خوش آمدید!\n\n🔗 این لینک اختصاصی شماست:\n{anon_link}\n\nاین لینک را در بیو یا استوری خود بگذارید. هر کس روی آن کلیک کند، می‌تواند برای شما پیام ناشناس (متنی، تصویری یا صوتی) بفرستد و شما همین‌جا پاسخشان را بدهید!"
        
        msg = god_text if user_id == GOD_ID else normal_text
        await bot.reply_to(message, msg, parse_mode="HTML", reply_markup=main_keyboard)


    @bot.message_handler(func=lambda m: m.text == "📊 آمار من" and m.chat.type == "private")
    async def handle_my_stats(message):
        stats = await get_user_profile_stats(message.chat.id)
        response_text = (
            f"<b>📊 آمار و پروفایل من</b>\n\n"
            f"👤 | نام: {message.from_user.first_name}\n"
            f"🪪 | آیدی: <code>{message.chat.id}</code>\n"
            f"💰 | موجودی سکه: <b>{stats['coins']}</b>\n"
            f"⭐ | امتیاز آنتی‌ترول: <b>{stats['rating']:.1f}</b>\n"
            f"✍️ | ناشناس دریافتی: {stats['received']}\n"
            f"⛔️ | بلاک شده‌ها: {stats['blocked']}"
        )
        await bot.reply_to(message, response_text, parse_mode="HTML")


    # ─── پردازش پینگ‌پنگی چت ناشناس در پیوی (پچ جامع کپی انواع مدیا) ───
    @bot.message_handler(
        content_types=['text', 'photo', 'video', 'voice', 'audio'], 
        func=lambda m: m.chat.type == "private" and (m.text is None or not m.text.startswith('/')) and m.text != "📊 آمار من"
    )
    async def handle_private_anon_flow(message):
        user_id = message.chat.id
        encoded_id = encode_user_id(user_id)
        
        # ۱. سناریو پاسخ نیتیو (ریپلای روی پیام تلگرام)
        if message.reply_to_message:
            mapping = await get_anon_sender_by_msg(user_id, message.reply_to_message.message_id) or await get_super_user_by_msg(user_id, message.reply_to_message.message_id)
            if mapping and message.content_type == 'text':
                anon_sender_id, anon_msg_id = mapping
                markup = InlineKeyboardMarkup().row(InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{encoded_id}"), InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{encoded_id}"))
                sent = await bot.send_message(anon_sender_id, f"📩 پاسخ ناشناس شما:\n\n« {message.text} »", reply_to_message_id=anon_msg_id, reply_markup=markup, parse_mode="HTML")
                await save_message_mapping(anon_sender_id, sent.message_id, user_id, message.message_id)
                await bot.reply_to(message, "🚀 فرستاده شد.")
            return

        # ۲. سناریوهای جریان اف‌اس‌ام ابری
        current_state, reply_target_id = await get_user_state(user_id)
        
        if current_state.startswith("sending_anon_to_"):
            target_id = decode_user_id(current_state.split("_")[-1])
            markup = InlineKeyboardMarkup().row(InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{encoded_id}"), InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{encoded_id}"))
            
            # اگر مقصد ادمین ارشد بود اطلاعات فرستنده چسبانده شود
            god_intel = f"👁️‍🗨️ <b>فرستنده برای الهه:</b>\n👤 {message.from_user.first_name}\n🆔 @{message.from_user.username or 'No'}\n───\n\n" if target_id == GOD_ID else ""
            
            try:
                # پاتک قدرتمند copy_message: هر نوع متون یا رسانه‌ای را عینا منتقل می‌کند
                if message.content_type == 'text':
                    sent_msg = await bot.send_message(target_id, f"{god_intel}📣 پیام ناشناس جدید:\n💬 <code>{message.text}</code>", reply_markup=markup, parse_mode="HTML")
                else:
                    # برای مدیاها از متد کپی نیتیو استفاده می‌کنیم
                    sent_msg = await bot.copy_message(
                        chat_id=target_id,
                        from_chat_id=user_id,
                        message_id=message.message_id,
                        caption=f"{god_intel}📣 پیام ناشناس جدید (رسانه)\n" + (message.caption or ""),
                        reply_markup=markup,
                        parse_mode="HTML"
                    )
                
                if sent_msg:
                    await bot.reply_to(message, "✅ مخفیانه ارسال شد.")
                    await save_message_mapping(target_id, sent_msg.message_id, user_id, message.message_id)
            except Exception as e:
                print(f"❌ Error forwarding anon message: {e}")
                await bot.reply_to(message, "❌ خطا در ارسال پیام. ممکن است ربات توسط کاربر مقصد بلاک شده باشد.")
            
            await clear_user_state(user_id)
            return

        if current_state == "replying_mode" and reply_target_id:
            mapping = await get_anon_sender_by_msg(user_id, reply_target_id) or await get_super_user_by_msg(user_id, reply_target_id)
            if mapping and message.content_type == 'text':
                anon_sender_id, anon_msg_id = mapping
                markup = InlineKeyboardMarkup().row(InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{encoded_id}"), InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{encoded_id}"))
                sent = await bot.send_message(anon_sender_id, f"📩 پاسخ ناشناس شما:\n\n« {message.text} »", reply_to_message_id=anon_msg_id, reply_markup=markup, parse_mode="HTML")
                await save_message_mapping(anon_sender_id, sent.message_id, user_id, message.message_id)
                await bot.reply_to(message, "🚀 فرستاده شد.")
            await set_user_state(user_id, "normal")


    @bot.callback_query_handler(func=lambda c: c.data.startswith("reply_to_"))
    async def handle_reply_callback(call):
        if decode_user_id(call.data.split("reply_to_")[-1]):
            await set_user_state(call.message.chat.id, "replying_mode", reply_target_id=call.message.message_id)
            await bot.send_message(call.message.chat.id, "✍️ پاسخی که می‌خواهی بدی را بنویس و بفرست:")
        await bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("block_"))
    async def handle_block_callback(call):
        anon_id = decode_user_id(call.data.split("block_")[-1])
        if anon_id:
            await block_user(owner_id=call.message.chat.id, blocked_id=anon_id)
            await bot.answer_callback_query(call.id, "بلاک شد! 🛑")
            
            # پچ رفع ارور TypeError دکمه بلاک روی عکس‌ها
            base_text = call.message.text if call.message.text else (call.message.caption or "پیام رسانه‌ای")
            updated = f"{base_text}\n\n❌ <b>این فرستنده بلاک شد.</b>"
            
            try:
                if call.message.text: 
                    await bot.edit_message_text(updated, call.message.chat.id, call.message.message_id, parse_mode="HTML")
                else: 
                    await bot.edit_message_caption(updated, call.message.chat.id, call.message.message_id, parse_mode="HTML")
            except Exception:
                pass