import time
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.config import EMOJI, GOD_ID
from src.database.db_manager import (
    get_user_chat_status_ext, join_random_chat_queue, leave_random_chat_queue,
    update_user_gender, disconnect_active_chat, get_or_create_short_link,
    get_user_id_by_short_code, submit_user_rating, add_to_chat_history_match,
    get_complete_user_context,
)
from src.bot.redis_config import redis_client, cache_invalidate_user, send_bot_log

# No circular import anymore — private_anon no longer imports from random_chat
from src.bot.handlers.private_anon import get_keyboards


def register_random_chat_handlers(bot: AsyncTeleBot):

    # ── Start random chat ─────────────────────────────────
    @bot.message_handler(
        func=lambda m: m.text == "🎲 شروع چت تصادفی" and m.chat.type == "private"
    )
    async def handle_start_random_chat(message):
        user_id                        = message.chat.id
        status, _, coins, gender       = await get_user_chat_status_ext(user_id)
        kb_main, kb_search, kb_chatting = get_keyboards()

        if status == 'chatting':
            await bot.reply_to(
                message,
                f"{EMOJI['caution']['html']} شما در یک چت فعال هستید! اول باید با دکمه زیر چت قبلی رو قطع کنی.",
                reply_markup=kb_chatting
            )
            return

        if status == 'searching':
            await bot.reply_to(
                message,
                f"{EMOJI['magnifiyer']['html']} شما در صف جستجو هستید...",
                reply_markup=kb_search
            )
            return

        if not gender:
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton(text=f"{EMOJI['right']['char']} پسرم",  callback_data="set_gender_male"),
                InlineKeyboardButton(text=f"{EMOJI['left']['char']} دخترم",  callback_data="set_gender_female"),
            )
            await bot.reply_to(
                message,
                f"{EMOJI['caution']['html']} <b>برای استفاده از چت تصادفی ابتدا باید جنسیت خودت رو تعیین کنی:</b>\n"
                "(این اطلاعات فقط یک‌بار دریافت میشه و قابل تغییر نیست)",
                parse_mode="HTML", reply_markup=markup
            )
            return

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            text=f"{EMOJI['sus']['char']} شانسی و کاملاً رایگان",
            callback_data="filter_any"
        ))
        markup.row(
            InlineKeyboardButton(text=f"{EMOJI['right']['char']} فقط اتصال به پسر (۳ سکه)", callback_data="filter_male"),
            InlineKeyboardButton(text=f"{EMOJI['left']['char']} فقط اتصال به دختر (۳ سکه)",  callback_data="filter_female"),
        )
        await bot.reply_to(
            message,
            f"{EMOJI['thunder']['html']} <b>نوع اتصال چت تصادفی رو انتخاب کن:</b>\n"
            f"{EMOJI['coin']['html']} موجودی فعلی شما: {coins} سکه",
            parse_mode="HTML", reply_markup=markup
        )

    # ── Gender registration ───────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith("set_gender_"))
    async def handle_set_gender_callback(call):
        gender   = call.data.split("set_gender_")[-1]
        user_id  = call.message.chat.id
        await update_user_gender(user_id, gender)

        # FIX: log call.from_user context via a fake-ish approach —
        # send_bot_log expects a message object; for callbacks log manually
        await send_bot_log(bot, call.message, "ثبت جنسیت نهایی", f"جنسیت: {gender}")

        await bot.answer_callback_query(call.id, "جنسیت شما با موفقیت ثبت شد! 🎉")
        await bot.edit_message_text(
            f"{EMOJI['crcl_yes']['html']} جنسیت شما ثبت شد. "
            "حالا می‌توانی دوباره دکمه 🎲 <b>شروع چت تصادفی</b> را بزنی!",
            user_id, call.message.message_id, parse_mode="HTML"
        )

    # ── Filter selection & queue entry ────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith("filter_"))
    async def handle_filter_selection_callback(call):
        target_gender                  = call.data.split("filter_")[-1]
        user_id                        = call.message.chat.id
        status, _, coins, _            = await get_user_chat_status_ext(user_id)
        kb_main, kb_search, _          = get_keyboards()

        if target_gender in ('male', 'female') and coins < 3:
            await bot.answer_callback_query(call.id, "❌ سکه کافی نداری!", show_alert=True)
            return

        await bot.answer_callback_query(call.id, "وارد صف شدی 🚀")
        await bot.delete_message(user_id, call.message.message_id)

        await join_random_chat_queue(user_id, target_gender)
        await cache_invalidate_user(user_id)

        filter_text = "شانسی" if target_gender == "any" else ("پسر" if target_gender == "male" else "دختر")
        await send_bot_log(bot, call.message, "ورود به صف", f"فیلتر: {filter_text}")

        search_msg = await bot.send_message(
            user_id,
            f"{EMOJI['magnifiyer']['html']} <b>[فیلتر: {filter_text}]</b> در حال جستجو برای کاربر هم‌سطح...",
            parse_mode="HTML", reply_markup=kb_search
        )

        if redis_client:
            await redis_client.zadd("match_queue", {str(user_id): time.time()})
            await redis_client.hset(f"search_meta:{user_id}", mapping={
                "msg_id":      search_msg.message_id,
                "filter_text": filter_text,
                "stage":       1,
            })

    # ── Cancel queue ──────────────────────────────────────
    @bot.message_handler(
        func=lambda m: m.text == "❌ انصراف از صف جستجو" and m.chat.type == "private"
    )
    async def handle_cancel_queue(message):
        user_id    = message.chat.id
        kb_main, _, _ = get_keyboards()

        await leave_random_chat_queue(user_id)
        await cache_invalidate_user(user_id)

        if redis_client:
            await redis_client.zrem("match_queue", str(user_id))
            await redis_client.delete(f"search_meta:{user_id}")

        await send_bot_log(bot, message, "انصراف از صف")
        await bot.reply_to(
            message,
            f"{EMOJI['banned']['html']} با موفقیت از صف خارج شدی و سکه‌هات برگشت خورد.",
            reply_markup=kb_main
        )

    # ── Disconnect active chat ────────────────────────────
    @bot.message_handler(
        func=lambda m: m.text == "🛑 قطع چت فعال" and m.chat.type == "private"
    )
    async def handle_disconnect_chat(message):
        user_id       = message.chat.id
        kb_main, _, _ = get_keyboards()

        context    = await get_complete_user_context(user_id)
        partner_id = context["active_partner_id"]

        await disconnect_active_chat(user_id)
        await cache_invalidate_user(user_id)
        if partner_id:
            await cache_invalidate_user(partner_id)

        await send_bot_log(bot, message, "قطع چت فعال", f"پارتنر: {partner_id}")
        await bot.reply_to(
            message,
            f"{EMOJI['banned']['html']} شما چت را قطع کردید. برای شروع مجدد دکمه 🎲 رو بزنید.",
            reply_markup=kb_main, parse_mode="HTML"
        )

        if not partner_id:
            return

        p_code = await get_or_create_short_link(partner_id)
        u_code = await get_or_create_short_link(user_id)

        markup_user = InlineKeyboardMarkup()
        markup_user.row(
            InlineKeyboardButton(text=f"{EMOJI['ok']['char']} لایک (+۱ سکه)",             callback_data=f"rate_like_{p_code}"),
            InlineKeyboardButton(text=f"{EMOJI['ban']['char']} دیس‌لایک و بلاک (+۱ سکه)", callback_data=f"rate_dis_{p_code}"),
        )
        await bot.send_message(
            user_id,
            f"{EMOJI['qe']['html']} <b>کیفیت چت چطور بود؟</b>\nبه پارتنرت امتیاز بده (+۱ سکه رایگان):",
            parse_mode="HTML", reply_markup=markup_user
        )

        markup_partner = InlineKeyboardMarkup()
        markup_partner.row(
            InlineKeyboardButton(text=f"{EMOJI['ok']['char']} لایک (+۱ سکه)",             callback_data=f"rate_like_{u_code}"),
            InlineKeyboardButton(text=f"{EMOJI['ban']['char']} دیس‌لایک و بلاک (+۱ سکه)", callback_data=f"rate_dis_{u_code}"),
        )
        try:
            await bot.send_message(
                partner_id,
                f"{EMOJI['caution']['html']} <b>پارتنر شما چت را قطع کرد.</b>\n"
                f"{EMOJI['qe']['html']} کیفیت چت چطور بود؟ (+۱ سکه هدیه):",
                parse_mode="HTML", reply_markup=kb_main
            )
            await bot.send_message(
                partner_id,
                f"{EMOJI['up']['html']} امتیاز خود به پارتنر سابق را ثبت کنید.",
                reply_markup=markup_partner
            )
        except Exception:
            pass

    # ── Rating callbacks ──────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith("rate_"))
    async def handle_rating_callbacks(call):
        parts      = call.data.split("_")
        action     = parts[1]           # "like" or "dis"
        partner_code = parts[-1]
        partner_id = await get_user_id_by_short_code(partner_code)
        user_id    = call.message.chat.id

        if not partner_id:
            await bot.answer_callback_query(call.id, "❌ خطای فنی در ثبت امتیاز.")
            return

        if action == "like":
            await submit_user_rating(partner_id, is_like=True, voter_id=user_id)
            await send_bot_log(bot, call.message, "ثبت لایک", f"پارتنر: {partner_id}")
            await bot.answer_callback_query(call.id, "ثبت شد و ۱ سکه هدیه گرفتی! 👍", show_alert=True)
            await bot.edit_message_text(
                f"{EMOJI['crcl_yes']['html']} بازخورد مثبتت ثبت شد و حساب شما شارژ گردید.",
                user_id, call.message.message_id
            )

        elif action == "dis":
            await submit_user_rating(partner_id, is_like=False, voter_id=user_id)
            await add_to_chat_history_match(user_id, partner_id, "dislike")
            await send_bot_log(bot, call.message, "ثبت دیس‌لایک", f"پارتنر بلاک: {partner_id}")
            await bot.answer_callback_query(call.id, "ثبت و بلاک شد و ۱ سکه هدیه گرفتی! 🛑", show_alert=True)
            await bot.edit_message_text(
                f"{EMOJI['banned']['html']} ثبت شد. این کاربر وارد لیست سیاه چت تصادفی شما شد و ۱ سکه هدیه دریافت کردی.",
                user_id, call.message.message_id
            )