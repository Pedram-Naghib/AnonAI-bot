from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReactionTypeEmoji

from src.config import SUPER_USERS
from src.database.db_manager import get_anon_sender_by_msg, get_super_user_by_msg


def register_reaction_handlers(bot: AsyncTeleBot):

    @bot.message_reaction_handler()
    async def handle_reactions(message_reaction):
        chat_id    = message_reaction.chat.id
        message_id = message_reaction.message_id

        if not message_reaction.new_reaction:
            return

        target_emoji = message_reaction.new_reaction[0].emoji

        if chat_id in SUPER_USERS:
            # Admin reacted to a received anon message — mirror to the original sender
            mapping = await get_anon_sender_by_msg(chat_id, message_id)
            if mapping:
                anon_sender_id, anon_msg_id = mapping
                try:
                    await bot.set_message_reaction(
                        anon_sender_id, anon_msg_id,
                        reaction=[ReactionTypeEmoji(target_emoji)]
                    )
                except Exception:
                    pass
        else:
            # Regular user reacted — mirror to whoever they're exchanging with
            mapping = (
                await get_super_user_by_msg(chat_id, message_id)
                or await get_anon_sender_by_msg(chat_id, message_id)
            )
            if mapping:
                target_id, target_msg_id = mapping
                try:
                    await bot.set_message_reaction(
                        target_id, target_msg_id,
                        reaction=[ReactionTypeEmoji(target_emoji)]
                    )
                except Exception:
                    pass