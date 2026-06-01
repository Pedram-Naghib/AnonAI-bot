from telebot.async_telebot import AsyncTeleBot
from src.config import GROUP_CHAT_ID
from src.database.db_manager import log_message_to_db

def register_group_handlers(bot: AsyncTeleBot):
    
    # ─── آلبوم‌ها و فایل‌های دسته‌جمعی گروه ───
    @bot.message_handler(func=lambda m: m.media_group_id is not None, content_types=['photo', 'video', 'audio'])
    async def handle_group_media_album(message):
        if message.chat.id == GROUP_CHAT_ID:
            if message.caption and not message.caption.startswith('/'):
                await log_message_to_db(
                    user_id=message.from_user.id,
                    username=message.from_user.username or "NoUsername",
                    first_name=message.from_user.first_name,
                    text=message.caption
                )
            return

    # ─── پیام‌های انفرادی، متنی و تک‌مدیای گروه ───
    @bot.message_handler(func=lambda m: m.media_group_id is None, content_types=['text', 'photo', 'video', 'voice', 'audio'])
    async def handle_group_single_messages(message):
        if message.chat.id == GROUP_CHAT_ID:
            log_text = message.text if message.content_type == 'text' else message.caption
            if log_text and not log_text.startswith('/'):
                await log_message_to_db(
                    user_id=message.from_user.id,
                    username=message.from_user.username or "NoUsername",
                    first_name=message.from_user.first_name,
                    text=log_text
                )
            return
        
        # پاتک امنیتی: اگر مال گروه غریبه بود کلاً ریترن شود
        elif message.chat.type in ['group', 'supergroup']:
            return