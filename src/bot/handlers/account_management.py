import html
import asyncio
from datetime import datetime, timedelta, timezone

from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.config import EMOJI
from src.database.db_manager import (
    get_user_profile_stats, get_or_create_short_link,
    get_complete_user_context, get_connection_pool,
)
from src.bot.redis_config import cache_invalidate_user, send_bot_log
from src.bot.handlers.private_anon import get_keyboards  # safe — no circular import


# ── Cooldown helper (used by both claim and dice handlers) ──
async def _check_daily_cooldown(conn, user_id: int):
    """
    Returns (eligible: bool, time_left_str: str | None).
    time_left_str is 'HH:MM' if still in cooldown, None if eligible.
    """
    row = await conn.fetchrow(
        "SELECT last_daily_bonus_at FROM users WHERE user_id = $1", user_id
    )
    if not row or not row['last_daily_bonus_at']:
        return True, None

    last_bonus = row['last_daily_bonus_at']
    if last_bonus.tzinfo is None:
        last_bonus = last_bonus.replace(tzinfo=timezone.utc)

    now       = datetime.now(timezone.utc)
    elapsed   = now - last_bonus
    if elapsed >= timedelta(days=1):
        return True, None

    time_left          = timedelta(days=1) - elapsed
    hours, remainder   = divmod(time_left.seconds, 3600)
    minutes, _         = divmod(remainder, 60)
    return False, f"{hours:02d}:{minutes:02d}"


def register_account_handlers(bot: AsyncTeleBot):

    # ── My stats ──────────────────────────────────────────
    @bot.message_handler(
        func=lambda m: m.text == "📊 آمار من" and m.chat.type == "private"
    )
    async def handle_my_stats(message):
        await send_bot_log(bot, message, "دکمه 📊 آمار من")
        stats      = await get_user_profile_stats(message.chat.id)
        gender_map = {"male": "🙋‍♂️ پسر", "female": "🙋‍♀️ دختر", None: "ثبت نشده ⚠️"}
        kb_main, _, _ = get_keyboards()

        await bot.reply_to(
            message,
            f"{EMOJI['100']['html']} <b>آمار و پروفایل من</b>\n\n"
            f"{EMOJI['profile']['html']} | نام: {html.escape(message.from_user.first_name or '')}\n"
            f"{EMOJI['id']['html']} | آیدی: <code>{message.chat.id}</code>\n"
            f"{EMOJI['green_dot']['html']} | جنسیت: <b>{gender_map[stats['gender']]}</b>\n"
            f"{EMOJI['coin']['html']} | موجودی سکه: <b>{stats['coins']}</b>\n"
            f"{EMOJI['gem']['html']} | امتیاز آنتی‌ترول: <b>{stats['rating']:.1f}</b>\n"
            f"{EMOJI['recieve']['html']} | ناشناس دریافتی: {stats['received']}\n"
            f"{EMOJI['send']['html']} | ناشناس ارسال شده: {stats['sent']}\n"
            f"{EMOJI['block']['html']} | بلاک شده‌ها: {stats['blocked']}",
            parse_mode="HTML", reply_markup=kb_main
        )

    # ── Coin wallet ───────────────────────────────────────
    @bot.message_handler(
        func=lambda m: m.text == "💰 سکه‌های من" and m.chat.type == "private"
    )
    async def handle_my_coins(message):
        await send_bot_log(bot, message, "دکمه 💰 سکه‌های من")
        stats  = await get_user_profile_stats(message.chat.id)

        inline_kb = InlineKeyboardMarkup()
        inline_kb.row(InlineKeyboardButton(
            text=f"{EMOJI['ball']['char']} شانس روزانه با مینی‌گیم تاس",
            callback_data="claim_daily"
        ))
        inline_kb.row(InlineKeyboardButton(
            text=f"{EMOJI['link']['char']} راهنمای کسب سکه رایگان",
            callback_data="coin_help"
        ))

        await bot.reply_to(
            message,
            f"{EMOJI['coin']['html']} <b>مدیریت کیف پول سکه</b>\n\n"
            f"{EMOJI['profile']['html']} | کاربر: {html.escape(message.from_user.first_name or '')}\n"
            f"{EMOJI['gem']['html']} | موجودی فعلی: <b>{stats['coins']} سکه</b>\n\n"
            f"{EMOJI['thunder']['html']} با سکه‌های خود می‌توانید در بخش 🎲 <b>چت تصادفی</b> به پارتنرهای هم‌سطح متصل شوید!",
            parse_mode="HTML", reply_markup=inline_kb
        )

    # ── Daily bonus: ask the user to send their own 🎲 ────
    @bot.callback_query_handler(func=lambda c: c.data == "claim_daily")
    async def handle_claim_daily_callback(call):
        user_id = call.message.chat.id
        pool    = await get_connection_pool()

        try:
            async with pool.acquire() as conn:
                eligible, time_left = await _check_daily_cooldown(conn, user_id)

            if not eligible:
                await bot.answer_callback_query(
                    call.id,
                    f"❌ شما امروز هدیه خود را گرفته‌اید!\n⏳ زمان باقی‌مانده: {time_left} ساعت",
                    show_alert=True
                )
                return

            # به جای دکمه شیشه‌ای، از کاربر می‌خواهیم خودش تاس بفرستد
            await bot.edit_message_text(
                f"{EMOJI['ball']['html']} <b>به مینی‌گیم بونوس روزانه خوش اومدی!</b>\n\n"
                "قوانین بازی عوض شده! حالا خودت باید تاس رو بندازی.\n"
                f"روی اموجی زیر کلیک کن تا کپی بشه و همون رو برام بفرست تا شانست رو بسنجم:\n\n"
                f"<code>🎲</code>",
                user_id, call.message.message_id,
                parse_mode="HTML"
            )
            await bot.answer_callback_query(call.id)

        except Exception as e:
            print(f"💥 Daily bonus check error: {e}")
            await bot.answer_callback_query(call.id, "❌ خطایی رخ داد.", show_alert=True)

    # ── Daily bonus: roll dice & credit (User sent dice) ──
    @bot.message_handler(content_types=['dice'], func=lambda m: m.chat.type == "private")
    async def handle_user_dice_roll(message):
        user_id = message.chat.id
        
        # مطمئن می‌شویم که کاربر حتماً تاس (🎲) فرستاده باشد، نه دارت یا بسکتبال
        if message.dice.emoji != "🎲":
            return

        pool = await get_connection_pool()
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    eligible, time_left = await _check_daily_cooldown(conn, user_id)
                    if not eligible:
                        await bot.reply_to(message, f"⚠️ شما قبلاً شانس امروز رو بازی کردید.\n⏳ زمان باقی‌مانده: {time_left} ساعت")
                        return

                    dice_value = message.dice.value
                    
                    # واریز سکه به حساب کاربر
                    await conn.execute(
                        "UPDATE users SET coins = coins + $1, last_daily_bonus_at = NOW() WHERE user_id = $2",
                        dice_value, user_id
                    )

            await cache_invalidate_user(user_id)
            
            # ۳ ثانیه صبر می‌کنیم تا انیمیشن تاس کاربر روی صفحه تمام شود
            await asyncio.sleep(3)

            if dice_value <= 2:
                result = (
                    f"{EMOJI['ball']['html']} تاس روی عدد <b>{dice_value}</b> ایستاد!\n\n"
                    f"{EMOJI['dislike']['html']} <b>ریدم تو شانست، فردا امتحان کن رفیق!</b>\n"
                    f"{EMOJI['coin']['html']} کیف پول شما فقط <b>+{dice_value} سکه</b> شارژ شد."
                )
            elif dice_value <= 4:
                result = (
                    f"{EMOJI['ball']['html']} تاس روی عدد <b>{dice_value}</b> ایستاد!\n\n"
                    f"{EMOJI['sus']['html']} <b>نه بد بود نه خوب، کاملاً معمولی!</b>\n"
                    f"{EMOJI['coin']['html']} کیف پول شما <b>+{dice_value} سکه</b> شارژ شد.\n"
                    f"{EMOJI['clock']['html']} ۲۴ ساعت دیگه بیا تا دوباره تست کنی."
                )
            elif dice_value == 5:
                result = (
                    f"{EMOJI['ball']['html']} تاس روی عدد <b>{dice_value}</b> ایستاد!\n\n"
                    f"{EMOJI['fire']['html']} <b>اوه چسبید! شانس بالا رو زدی!</b>\n"
                    f"{EMOJI['coin']['html']} کیف پول شما <b>+{dice_value} سکه رایگان</b> شارژ شد.\n"
                    f"{EMOJI['thunder']['html']} پرانرژی ادامه بده!"
                )
            else:  # 6
                result = (
                    f"{EMOJI['thunder']['html']} <b>بووووم! تاس روی عدد جادویی ۶ ایستاد!</b> {EMOJI['gem']['html']}\n\n"
                    f"{EMOJI['present']['html']} بالاترین پاداش ممکن! <b>+۶ سکه رایگان</b> به حسابت اضافه شد.\n"
                    f"{EMOJI['clock']['html']} ۲۴ ساعت دیگه منتظرتم!"
                )

            await bot.reply_to(message, result, parse_mode="HTML")

        except Exception as e:
            print(f"💥 Dice roll error: {e}")
            await bot.reply_to(message, f"{EMOJI['caution']['html']} خطای فنی در سیستم تاس‌اندازی رخ داد.", parse_mode="HTML")

    # ── Coin help ─────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == "coin_help")
    async def handle_coin_help_callback(call):
        user_id  = call.message.chat.id
        bot_info = await bot.get_me()

        my_short_code = await get_or_create_short_link(user_id)
        ref_link      = f"https://t.me/{bot_info.username}?start={my_short_code}"

        await bot.send_message(
            user_id,
            f"{EMOJI['mail']['html']} <b>راهنمای جامع سیستم اقتصاد سکه</b>\n\n"
            f"{EMOJI['coin']['html']} <b>سکه چیست؟</b>\nواحد مالی ربات برای اتصال در چت تصادفی.\n\n"
            f"{EMOJI['thunder']['html']} <b>راه‌های کسب سکه رایگان:</b>\n\n"
            f"{EMOJI['one']['html']} <b>استارت اولیه:</b> <b>۱۰ سکه رایگان</b> هدیه.\n\n"
            f"{EMOJI['two']['html']} <b>پاداش شانس روزانه:</b> هر ۲۴ ساعت با تاس بین <b>۱ تا ۶ سکه</b> جایزه بگیر!\n\n"
            f"{EMOJI['three']['html']} <b>امتیازدهی آنتی‌ترول:</b> بعد از هر چت، به پارتنر امتیاز بده و <b>۱ سکه</b> هدیه بگیر.\n\n"
            f"{EMOJI['four']['html']} <b>سیستم رفرال:</b>\n<code>{ref_link}</code>\n\n"
            f"{EMOJI['light']['html']} لینک ناشناس و لینک دعوت یکسان‌اند! دوستانت هم می‌توانند ناشناس پیام بفرستند.\n\n"
            f"{EMOJI['five']['html']} <b>جریمه معطلی:</b> اگر ۱۵ دقیقه در صف بمانی و کسی پیدا نشود، ۲ سکه رایگان هدیه می‌گیری!",
            parse_mode="HTML"
        )
        await bot.answer_callback_query(call.id)

    # ── Delete account (step 1: confirm) ─────────────────
    @bot.message_handler(
        func=lambda m: m.text == "❌ حذف کامل اطلاعات من" and m.chat.type == "private"
    )
    async def handle_request_delete_account(message):
        user_id = message.chat.id
        await send_bot_log(bot, message, "درخواست حذف اطلاعات")

        context = await get_complete_user_context(user_id)
        if context["chat_status"] == 'chatting':
            await bot.reply_to(
                message,
                f"{EMOJI['caution']['html']} شما در یک چت فعال هستید! ابتدا چت را قطع کنید."
            )
            return

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton(text=f"{EMOJI['crcl_yes']['char']} بله، مطمئنم",   callback_data="confirm_delete_my_data"),
            InlineKeyboardButton(text=f"{EMOJI['crcl_no']['char']} خیر، منصرف شدم", callback_data="cancel_delete_my_data"),
        )
        await bot.reply_to(
            message,
            f"{EMOJI['red_caution']['html']} <b>هشدار بسیار مهم!</b>\n\n"
            "با تایید این دستور، تمام اطلاعات شما شامل:\n"
            "• لینک ناشناس اختصاصی\n"
            "• تاریخچه پیام‌های ناشناس\n"
            "• لیست سیاه چت تصادفی\n"
            "<b>برای همیشه و بدون بازگشت پاک خواهد شد!</b>\n\n"
            "آیا کاملاً مطمئن هستید؟",
            parse_mode="HTML", reply_markup=markup
        )

    # ── Delete account (step 2: execute) ─────────────────
    @bot.callback_query_handler(
        func=lambda c: c.data in ["confirm_delete_my_data", "cancel_delete_my_data"]
    )
    async def handle_delete_account_callbacks(call):
        user_id = call.message.chat.id

        if call.data == "cancel_delete_my_data":
            await bot.answer_callback_query(call.id, "عملیات حذف لغو شد. 😌")
            await bot.edit_message_text(
                f"{EMOJI['crcl_yes']['html']} عملیات لغو شد. اطلاعات شما کاملاً امن باقی ماند.",
                user_id, call.message.message_id
            )
            return

        await bot.answer_callback_query(call.id, "در حال پاکسازی... ⏳", show_alert=True)

        from src.bot.redis_config import redis_client
        if redis_client:
            await redis_client.zrem("match_queue", str(user_id))
            await redis_client.delete(f"search_meta:{user_id}")
        await cache_invalidate_user(user_id)

        pool = await get_connection_pool()
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM user_links        WHERE user_id = $1", user_id)
                    await conn.execute("DELETE FROM random_chat_blocks WHERE user_id = $1 OR blocked_partner_id = $1", user_id)
                    await conn.execute("DELETE FROM message_map        WHERE user_chat_id = $1 OR anon_sender_id = $1", user_id)
                    await conn.execute("""
                        UPDATE users SET
                            anon_state        = 'normal',
                            reply_target_id   = NULL,
                            coins             = 10,
                            rating            = 5.0,
                            rating_count      = 0,
                            chat_status       = 'idle',
                            active_partner_id = NULL,
                            queue_joined_at   = NULL,
                            target_gender     = 'any',
                            total_received    = 0,
                            total_sent        = 0
                        WHERE user_id = $1
                    """, user_id)

            await cache_invalidate_user(user_id)
            await bot.edit_message_text(
                f"{EMOJI['trash']['html']} <b>پاکسازی با موفقیت انجام شد!</b>\n\n"
                "تمام ردپای شما پاک شد و حساب به حالت اولیه (۱۰ سکه) برگشت.",
                user_id, call.message.message_id, parse_mode="HTML"
            )

        except Exception as e:
            print(f"💥 Failed to wipe user data: {e}")
            await bot.edit_message_text(
                f"{EMOJI['crcl_no']['html']} خطای فنی رخ داد. لطفاً بعداً تلاش کنید.",
                user_id, call.message.message_id
            )

    # ── Clear blocklist ───────────────────────────────────
    @bot.message_handler(
        func=lambda m: m.text == "🗑️ خالی کردن لیست سیاه" and m.chat.type == "private"
    )
    async def handle_request_clear_blocklist(message):
        user_id = message.chat.id
        await send_bot_log(bot, message, "درخواست مدیریت لیست سیاه")

        context = await get_complete_user_context(user_id)
        if context["chat_status"] == 'chatting':
            await bot.reply_to(
                message,
                f"{EMOJI['caution']['html']} شما در یک چت فعال هستید! ابتدا گفتگو را قطع کنید."
            )
            return

        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton(
            text=f"{EMOJI['ball']['char']} لیست سیاه چت تصادفی",
            callback_data="clear_bl_random"
        ))
        markup.row(InlineKeyboardButton(
            text=f"{EMOJI['mail']['char']} لیست سیاه پیام ناشناس (پیوی)",
            callback_data="clear_bl_anon"
        ))
        await bot.reply_to(
            message,
            f"{EMOJI['trash']['html']} <b>کدام لیست سیاه را می‌خواهید خالی کنید؟</b>",
            parse_mode="HTML", reply_markup=markup
        )

    # ── Clear blocklist: execute ──────────────────────────
    @bot.callback_query_handler(
        func=lambda c: c.data in ["clear_bl_random", "clear_bl_anon"]
    )
    async def handle_clear_blocklist_execution(call):
        user_id = call.message.chat.id
        pool    = await get_connection_pool()

        try:
            async with pool.acquire() as conn:
                if call.data == "clear_bl_random":
                    await conn.execute("DELETE FROM random_chat_blocks WHERE user_id = $1", user_id)
                    await cache_invalidate_user(user_id)
                    await bot.edit_message_text(
                        f"{EMOJI['crcl_yes']['html']} <b>لیست سیاه چت تصادفی خالی شد!</b>\n"
                        "ممکن است دوباره به پارتنرهای سابق متصل شوید.",
                        user_id, call.message.message_id, parse_mode="HTML"
                    )
                else:
                    await conn.execute("DELETE FROM block_list WHERE owner_id = $1", user_id)
                    await cache_invalidate_user(user_id)
                    await bot.edit_message_text(
                        f"{EMOJI['crcl_yes']['html']} <b>لیست سیاه پیام ناشناس خالی شد!</b>\n"
                        "تمام بلاک‌شده‌ها می‌توانند مجدداً پیام ارسال کنند.",
                        user_id, call.message.message_id, parse_mode="HTML"
                    )
            await bot.answer_callback_query(call.id, "پاکسازی انجام شد 🧼")

        except Exception as e:
            print(f"💥 Blocklist clear error: {e}")
            await bot.answer_callback_query(call.id, "❌ خطای فنی.", show_alert=True)