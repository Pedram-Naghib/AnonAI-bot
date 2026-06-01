from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReactionTypeEmoji
from src.database.db_manager import get_anon_sender_by_msg, get_super_user_by_msg

SUPER_USERS = [247768888, 6779908406]

def register_reaction_handlers(bot: AsyncTeleBot):

    @bot.message_reaction_handler()
    async def handle_reactions(message_reaction):
        chat_id = message_reaction.chat.id
        message_id = message_reaction.message_id
        if not message_reaction.new_reaction: return
        target_emoji = message_reaction.new_reaction[0].emoji
        
        if chat_id in SUPER_USERS:
            mapping = await get_anon_sender_by_msg(chat_id, message_id)
            if mapping:
                anon_sender_id, anon_msg_id = mapping
                try: await bot.set_message_reaction(anon_sender_id, anon_msg_id, reaction=[ReactionTypeEmoji(target_emoji)])
                except Exception: pass
        else:
            mapping = await get_super_user_by_msg(chat_id, message_id) or await get_anon_sender_by_msg(chat_id, message_id)
            if mapping:
                super_user_id, super_msg_id = mapping
                try: await bot.set_message_reaction(super_user_id, super_msg_id, reaction=[ReactionTypeEmoji(target_emoji)])
                except Exception: pass