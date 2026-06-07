from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ۱. توابع خالص دیتابیسی را از db_manager می‌آوریم (بدون متدهای کش)
from src.database.db_manager import (
    get_user_profile_stats, claim_daily_bonus, get_or_create_short_link,
    get_complete_user_context, block_user
)

# ۲. متدهای مربوط به ردیس و مدیریت کش را دقیقاً از ماژول پرایوت می‌آوریم
from src.bot.handlers.private_anon import (
    redis_client, cache_invalidate_user, send_bot_log, get_keyboards
)

def register_account_handlers(bot: AsyncTeleBot):

    # ==========================================
    # 📊 هندلر متنی: نمایش پروفایل و آمار من
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "📊 آمار من" and m.chat.type == "private")
    async def handle_my_stats(message):
        await send_bot_log(bot, message, "دکمه 📊 آمار من")
        stats = await get_user_profile_stats(message.chat.id)
        gender_map = {"male": "🙋‍♂️ پسر", "female": "🙋‍♀️ دختر", None: "ثبت نشده ⚠️"}
        
        response_text = (
            f"<b>📊 آمار و پروفایل من</b>\n\n"
            f"👤 | نام: {message.from_user.first_name}\n"
            f"🪪 | آیدی: <code>{message.chat.id}</code>\n"
            f"⚥ | جنسیت من: <b>{gender_map[stats['gender']]}</b>\n"
            f"💰 | موجودی سکه: <b>{stats['coins']}</b>\n"
            f"⭐ | امتیاز آنتی‌ترول: <b>{stats['rating']:.1f}</b>\n"
            f"✍️ | ناشناس دریافتی: {stats['received']}\n"
            f"📤 | ناشناس ارسال شده: {stats['sent']}\n"
            f"⛔️ | بلاک شده‌ها: {stats['blocked']}"
        )
        kb_main, _, _ = get_keyboards()
        await bot.reply_to(message, response_text, parse_mode="HTML", reply_markup=kb_main)

    # ==========================================
    # 💰 هندلر متنی: مدیریت کیف پول سکه و منوی هدیه
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "💰 سکه‌های من" and m.chat.type == "private")
    async def handle_my_coins(message):
        await send_bot_log(bot, message, "دکمه 💰 سکه‌های من")
        user_id = message.chat.id
        stats = await get_user_profile_stats(user_id)
        
        inline_kb = InlineKeyboardMarkup()
        inline_kb.row(InlineKeyboardButton("🎁 دریافت ۵ سکه رایگان روزانه", callback_data="claim_daily"))
        inline_kb.row(InlineKeyboardButton("📜 راهنمای کسب سکه رایگان", callback_data="coin_help"))
        
        response_text = (
            f"<b>💰 مدیریت کیف پول سکه</b>\n\n"
            f"👤 | کاربر: {message.from_user.first_name}\n"
            f"🪙 | موجودی فعلی شما: <b>{stats['coins']} سکه</b>\n\n"
            f"⚡ با سکه‌های خود می‌توانید در بخش 🎲 <b>چت تصادفی</b> به پارتنرهای هم‌سطح متصل شوید!"
        )
        await bot.reply_to(message, response_text, parse_mode="HTML", reply_markup=inline_kb)

    # ==========================================
    # 🎁 کالبک تسویه هدیه ۵ سکه روزانه با کول‌داون اتمیک
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data == "claim_daily")
    async def handle_claim_daily_callback(call):
        user_id = call.message.chat.id
        res = await claim_daily_bonus(user_id)
        
        if res == "rewarded":
            await bot.answer_callback_query(call.id, "🎁 ۵ سکه هدیه به حسابت واریز شد!", show_alert=True)
            stats = await get_user_profile_stats(user_id)
            inline_kb = InlineKeyboardMarkup()
            inline_kb.row(InlineKeyboardButton("🎁 دریافت ۵ سکه رایگان روزانه", callback_data="claim_daily"))
            inline_kb.row(InlineKeyboardButton("📜 راهنمای کسب سکه رایگان", callback_data="coin_help"))
            new_text = (
                f"<b>💰 مدیریت کیف پول سکه</b>\n\n"
                f"👤 | کاربر: {call.from_user.first_name}\n"
                f"🪙 | موجودی فعلی شما: <b>{stats['coins']} سکه</b>\n\n"
                f"⚡ با سکه‌های خود می‌توانید در بخش 🎲 <b>چت تصادفی</b> به پارتنرهای هم‌سطح متصل شوید!"
            )
            try: await bot.edit_message_text(new_text, user_id, call.message.message_id, parse_mode="HTML", reply_markup=inline_kb)
            except Exception: pass
        else:
            time_left = res.split("cooldown_")[-1]
            await bot.answer_callback_query(call.id, f"❌ شما امروز هدیه خود را گرفته‌اید!\n⏳ زمان باقی‌مانده: {time_left} ساعت", show_alert=True)

    # ==========================================
    # 📜 کالبک راهنمای جامع کسب سکه و رفرال سیستم
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data == "coin_help")
    async def handle_coin_help_callback(call):
        await send_bot_log(bot, call.message, "کالبک شیشه‌ای coin_help", "باز کردن راهنمای جامع اقتصاد ربات")
        user_id = call.message.chat.id
        bot_info = await bot.get_me()
        
        my_short_code = await get_or_create_short_link(user_id)
        ref_link = f"https://t.me/{bot_info.username}?start={my_short_code}"  
        
        help_text = (
            f"<b>📜 راهنمای جامع سیستم اقتصاد سکه</b>\n\n"
            f"🪙 <b>سکه چیست؟</b>\n"
            f"واحد مالی ربات برای برقراری اتصال در چت تصادفی است.\n\n"
            f"🚀 <b>راه‌های کسب سکه رایگان:</b>\n\n"
            f"۱. <b>استارت اولیه:</b> هر کاربر در عادی‌ترین حالت ورود <b>۱۰ سکه رایگان</b> هدیه می‌گیرد.\n\n"
            f"۲. <b>🎁 پاداش شانس روزانه:</b> با زدن دکمه شیشه‌ای هدیه در بخش سکه‌ها، هر ۲۴ ساعت یک‌بار <b>۵ سکه کاملاً رایگان</b> هدیه بگیرید!\n\n"
            f"۳. <b>⭐ پاداش آنتی‌ترول (امتیازدهی):</b> بعد از اتمام هر چت تصادفی, به کیفیت رفتار پارتنرتان امتیاز (لایک یا دیس‌لایک) بدهید و <b>۱ سکه رایگان</b> به عنوان پاداش مشارکت از ربات هدیه بگیرید!\n\n"
            f"۴. <b>سیستم رفرال (دعوت دوستان):</b> این لینک اختصاصی شماست:\n"
            f"<code>{ref_link}</code>\n\n"
            f"💡 <b>یک تیر و دو نشان:</b> لینک ناشناس و لینک دعوت شما کاملاً یکسان هستند! دوستانتان هم می‌توانند به شما پیام ناشناس بفرستند و همزمان اگر قبلاً عضو ربات نبوده باشند، زیرمجموعهٔ شما ثبت خواهند شد.\n\n"
            f"۵. <b>جریمه معطلی ربات:</b> اگر در صف جستجو وارد شوید و به دلیل شلوغی تا ۱۵ دقیقه پارتنری برای شما پیدا نشد، ۲ سکه رایگان هم به عنوان جریمه از طرف ربات دریافت می‌کنید! (دارای کول‌داون ۳ ساعته)"
        )
        await bot.send_message(user_id, help_text, parse_mode="HTML")
        await bot.answer_callback_query(call.id)

    # ==========================================
    # ⚠️ هندلر متنی: درخواست حذف کامل اطلاعات (گام اول)
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "❌ حذف کامل اطلاعات من" and m.chat.type == "private")
    async def handle_request_delete_account(message):
        user_id = message.chat.id
        await send_bot_log(bot, message, "درخواست حذف اطلاعات")
        
        context = await get_complete_user_context(user_id)
        if context["chat_status"] == 'chatting':
            await bot.reply_to(message, "⚠️ شما در یک چت فعال هستید! ابتدا چت را قطع کنید.")
            return

        markup_confirm = InlineKeyboardMarkup().row(
            InlineKeyboardButton("✅ بله، مطمئنم و پاک کن", callback_data="confirm_delete_my_data"),
            InlineKeyboardButton("❌ خیر، منصرف شدم", callback_data="cancel_delete_my_data")
        )
        
        warning_text = (
            "⚠️ <b>هشدار بسیار مهم!</b>\n\n"
            "با تایید این دستور، تمام اطلاعات شما شامل:\n"
            "• لینک ناشناس اختصاصی شما\n"
            "• تاریخچه پیام‌های ناشناس ارسالی و دریافتی\n"
            "• لیست سیاه چت تصادفی شما\n"
            "<b>برای همیشه و بدون بازگشت پاک خواهد شد!</b>\n\n"
            "آیا کاملاً مطمئن هستید؟"
        )
        await bot.reply_to(message, warning_text, parse_mode="HTML", reply_markup=markup_confirm)

    # ==========================================
    # ⚠️ کالبک تایید نهایی و پاکسازی اتمیک جداول دیتابیس (گام دوم)
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data in ["confirm_delete_my_data", "cancel_delete_my_data"])
    async def handle_delete_account_callbacks(call):
        user_id = call.message.chat.id
        kb_main, _, _ = get_keyboards()
        
        if call.data == "cancel_delete_my_data":
            await bot.answer_callback_query(call.id, "عملیات حذف لغو شد. 😌")
            await bot.edit_message_text("✅ عملیات لغو شد. اطلاعات شما کاملاً امن باقی ماند.", user_id, call.message.message_id)
            return

        await bot.answer_callback_query(call.id, "در حال پاکسازی اطلاعات... ⏳", show_alert=True)
        
        if redis_client:
            await redis_client.zrem("match_queue", str(user_id))
            await redis_client.delete(f"search_meta:{user_id}")
        await cache_invalidate_user(user_id)

        from src.database.db_manager import get_connection_pool
        pool = await get_connection_pool()
        
        try:
            async with pool.acquire() as conn:
                tx = conn.transaction()
                await tx.start()
                try:
                    await conn.execute("DELETE FROM user_links WHERE user_id = $1", user_id)
                    await conn.execute("DELETE FROM random_chat_blocks WHERE user_id = $1 OR blocked_partner_id = $1", user_id)
                    await conn.execute("DELETE FROM message_map WHERE user_chat_id = $1 OR anon_sender_id = $1", user_id)
                    
                    await conn.execute("""
                        UPDATE users SET 
                            anon_state = 'normal', 
                            reply_target_id = NULL, 
                            coins = 10, 
                            rating = 5.0, 
                            rating_count = 0, 
                            chat_status = 'idle', 
                            active_partner_id = NULL, 
                            queue_joined_at = NULL, 
                            target_gender = 'any' 
                        WHERE user_id = $1
                    """, user_id)
                    
                    await tx.commit()
                    await cache_invalidate_user(user_id)
                    
                    await send_bot_log(bot, call.message, "💥 حذف کامل اطلاعات کاربری انجام شد")
                    await bot.edit_message_text("🧼 <b>پاکسازی با موفقیت انجام شد!</b>\n\nتمام ردپای شما پاک شد، لینک ناشناس سابق شما باطل گردید و حساب شما به حالت اولیه (۱۰ سکه) برگشت. برای شروع مجدد می‌توانید منو را لمس کنید:", user_id, call.message.message_id, parse_mode="HTML")
                    
                except Exception as tx_err:
                    await tx.rollback()
                    raise tx_err
                    
        except Exception as err:
            print(f"💥 Failed to wipe user data: {err}")
            await bot.edit_message_text("❌ خطای فنی در پاکسازی دیتابیس رخ داد. لطفا بعداً تلاش کنید.", user_id, call.message.message_id)

    # ==========================================
    # 🗑️ هندلر متنی: منوی تفکیک خالی کردن لیست‌های سیاه
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "🗑️ خالی کردن لیست سیاه" and m.chat.type == "private")
    async def handle_request_clear_blocklist(message):
        user_id = message.chat.id
        await send_bot_log(bot, message, "درخواست مدیریت و خالی کردن لیست سیاه")
        
        context = await get_complete_user_context(user_id)
        if context["chat_status"] == 'chatting':
            await bot.reply_to(message, "⚠️ شما در یک چت فعال هستید! ابتدا گفتگو را قطع کنید.")
            return

        markup_selection = InlineKeyboardMarkup()
        markup_selection.row(InlineKeyboardButton("🎲 لیست سیاه چت تصادفی", callback_data="clear_bl_random"))
        markup_selection.row(InlineKeyboardButton("📩 لیست سیاه پیام ناشناس (پیوی)", callback_data="clear_bl_anon"))
        
        await bot.reply_to(
            message, 
            "🗑️ <b>کدام یک از لیست‌های سیاه خود را می‌خواهید کاملاً خالی کنید؟</b>\n\n"
            "یکی از گزینه‌های زیر را انتخاب کنید:", 
            parse_mode="HTML", 
            reply_markup=markup_selection
        )

    # ==========================================
    # ⚠️ کالبک‌های نهایی پاکسازی اتمیک لیست انتخاب شده
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data in ["clear_bl_random", "clear_bl_anon"])
    async def handle_clear_blocklist_execution(call):
        user_id = call.message.chat.id
        action_type = call.data
        
        from src.database.db_manager import get_connection_pool
        pool = await get_connection_pool()
        
        try:
            async with pool.acquire() as conn:
                if action_type == "clear_bl_random":
                    await conn.execute("DELETE FROM random_chat_blocks WHERE user_id = $1", user_id)
                    await cache_invalidate_user(user_id)
                    
                    await send_bot_log(bot, call.message, "حذف لیست سیاه چت تصادفی")
                    await bot.edit_message_text(
                        "✅ <b>لیست سیاه چت تصادفی شما کاملاً خالی شد!</b>\n"
                        "از این به بعد ممکن است در سیستم مچ‌میکینگ دوباره به پارتنرهای سابق متصل شوید.", 
                        user_id, call.message.message_id, parse_mode="HTML"
                    )
                    
                elif action_type == "clear_bl_anon":
                    await conn.execute("DELETE FROM block_list WHERE owner_id = $1", user_id)
                    await cache_invalidate_user(user_id)
                    
                    await send_bot_log(bot, call.message, "حذف لیست سیاه پیام ناشناس")
                    await bot.edit_message_text(
                        "✅ <b>لیست سیاه پیام ناشناس شما کاملاً خالی شد!</b>\n"
                        "تمام کسانی که قبلاً آن‌ها را بلاک کرده بودید، از این به بعد می‌توانند مجدداً روی لینک شما پیام ناشناس ارسال کنند.", 
                        user_id, call.message.message_id, parse_mode="HTML"
                    )
                    
            await bot.answer_callback_query(call.id, "پاکسازی با موفقیت انجام شد 🧼")
        except Exception as err:
            print(f"💥 Failed to clear specific blocklist: {err}")
            await bot.answer_callback_query(call.id, "❌ خطای فنی در پاکسازی لیست سیاه.", show_alert=True)