import time
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# وارد کردن توابع پایه دیتابیس مورد نیاز برای چت تصادفی
from src.database.db_manager import (
    get_user_chat_status_ext, join_random_chat_queue, leave_random_chat_queue,
    update_user_gender, disconnect_active_chat, get_or_create_short_link,
    get_user_id_by_short_code, submit_user_rating, add_to_chat_history_match,
    get_complete_user_context, get_user_profile_stats
)

# 🔥 دریافت متدهای لایه خنثی کش و لاگر از فایل کانفیگ برای پاره کردن حلقه ایمپورت چرخشی
from src.config import EMOJI
from src.bot.redis_config import redis_client, cache_invalidate_user, send_bot_log

GOD_ID = 6779908406

def register_random_chat_handlers(bot: AsyncTeleBot):

    # ==========================================
    # 🎲 هندلر دکمه اصلی: شروع چت تصادفی و فیلترها
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "🎲 شروع چت تصادفی" and m.chat.type == "private")
    async def handle_start_random_chat(message):
        user_id = message.chat.id
        status, _, coins, gender = await get_user_chat_status_ext(user_id)
        
        # 🔥 پاتک لوکال ایمپورت: منوها را زمان اجرا فراخوانی می‌کنیم تا سیستم قفل نکند
        from src.bot.handlers.private_anon import get_keyboards
        kb_main, kb_search, kb_chatting = get_keyboards()
        
        if status == 'chatting':
            await bot.reply_to(message, f"{EMOJI['caution']} شما در یک چت فعال هستید! اول باید با دکمه زیر چت قبلی رو قطع کنی.", reply_markup=kb_chatting)
            return
        if status == 'searching':
            await bot.reply_to(message, f"{EMOJI['magnifiyer']} شما در صف جستجو هستید...", reply_markup=kb_search)
            return

        if not gender:
            markup_gender = InlineKeyboardMarkup().row(
                InlineKeyboardButton(text=f"{EMOJI['right']} پسرم", callback_data="set_gender_male"),
                InlineKeyboardButton(text=f"{EMOJI['left']} دخترم", callback_data="set_gender_female")
            )
            await bot.reply_to(message, f"{EMOJI['caution']} <b>برای استفاده از چت تصادفی ابتدا باید جنسیت خودت رو تعیین کنی:</b>\n(این اطلاعات فقط یک‌بار دریافت میشه و قابل تغییر نیست)", parse_mode="HTML", reply_markup=markup_gender)
            return

        markup_filter = InlineKeyboardMarkup().add(
            InlineKeyboardButton(text=f"{EMOJI['sus']} شانسی و کاملاً رایگان", callback_data="filter_any")
        ).row(
            InlineKeyboardButton(text=f"{EMOJI['right']} فقط اتصال به پسر (۳ سکه)", callback_data="filter_male"),
            InlineKeyboardButton(text=f"{EMOJI['left']} فقط اتصال به دختر (۳ سکه)", callback_data="filter_female")
        )
        await bot.reply_to(message, f"{EMOJI['thunder']} <b>نوع اتصال چت تصادفی رو انتخاب کن:</b>\n{EMOJI['coin']} موجودی فعلی شما: {coins} سکه", parse_mode="HTML", reply_markup=markup_filter)

    # ==========================================
    # ⚥ کالبک ثبت جنسیت اولیه کاربر
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("set_gender_"))
    async def handle_set_gender_callback(call):
        gender_selected = call.data.split("set_gender_")[-1]
        user_id = call.message.chat.id
        await update_user_gender(user_id, gender_selected)
        await send_bot_log(bot, call.message, "ثبت جنسیت نهایی", f"انتخاب جنسیت اصلی: {gender_selected}")
        await bot.answer_callback_query(call.id, "جنسیت شما با موفقیت ثبت شد! 🎉")
        await bot.edit_message_text(f"{EMOJI['crcl_yes']} جنسیت شما ثبت شد. حالا می‌توانی دوباره دکمه 🎲 <b>شروع چت تصادفی</b> را بزنی تا فیلترها باز شوند!", user_id, call.message.message_id, parse_mode="HTML")

    # ==========================================
    # 🚀 کالبک انتخاب فیلتر و ورود سریع به صف اولویت‌دار ردیس
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("filter_"))
    async def handle_filter_selection_callback(call):
        target_gender = call.data.split("filter_")[-1]
        user_id = call.message.chat.id
        status, _, coins, _ = await get_user_chat_status_ext(user_id)
        
        from src.bot.handlers.private_anon import get_keyboards
        kb_main, kb_search, kb_chatting = get_keyboards()

        if target_gender in ['male', 'female'] and coins < 3:
            await bot.answer_callback_query(call.id, "❌ سکه کافی نداری!", show_alert=True)
            return

        await bot.answer_callback_query(call.id, "وارد صف شدی 🚀")
        await bot.delete_message(user_id, call.message.message_id)
        
        await join_random_chat_queue(user_id, target_gender)
        await cache_invalidate_user(user_id)
        
        filter_text = "شانسی" if target_gender == "any" else ("پسر" if target_gender == "male" else "دختر")
        await send_bot_log(bot, call.message, "درخواست ورود به صف", f"نوع فیلتر انتخابی: {filter_text}")
        
        search_msg = await bot.send_message(user_id, f"{EMOJI['magnifiyer']} <b>[فیلتر: {filter_text}]</b> در حال جستجو برای کاربر هم‌سطح...", parse_mode="HTML", reply_markup=kb_search)
        
        if redis_client:
            await redis_client.zadd("match_queue", {str(user_id): time.time()})
            await redis_client.hset(f"search_meta:{user_id}", mapping={
                "msg_id": search_msg.message_id, 
                "filter_text": filter_text,
                "stage": 1
            })

    # ==========================================
    # ❌ هندلر متنی: انصراف از صف جستجو و برگشت سکه
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "❌ انصراف از صف جستجو" and m.chat.type == "private")
    async def handle_cancel_queue(message):
        user_id = message.chat.id
        await leave_random_chat_queue(user_id)
        await cache_invalidate_user(user_id)
        
        if redis_client:
            await redis_client.zrem("match_queue", str(user_id))
            await redis_client.delete(f"search_meta:{user_id}")
            
        await send_bot_log(bot, message, "دکمه ❌ انصراف از صف")
        
        from src.bot.handlers.private_anon import get_keyboards
        kb_main, _, _ = get_keyboards()
        await bot.reply_to(message, f"{EMOJI['banned']} با موفقیت از صف جستجو خارج شدی و سکه‌هات برگشت خورد.", reply_markup=kb_main)

    # ==========================================
    # 🛑 هندلر متنی: قطع چت فعال و بازخورد سیستم آنتی‌ترول
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "🛑 قطع چت فعال" and m.chat.type == "private")
    async def handle_disconnect_chat(message):
        user_id = message.chat.id
        
        from src.bot.handlers.private_anon import get_keyboards
        kb_main, _, _ = get_keyboards()
        
        context = await get_complete_user_context(user_id)
        partner_id = context["active_partner_id"]
        
        await disconnect_active_chat(user_id)
        await cache_invalidate_user(user_id)
        if partner_id:
            await cache_invalidate_user(partner_id)
        
        await send_bot_log(bot, message, "دکمه 🛑 قطع چت فعال", f"قطع ارتباط با پارتنر: {partner_id}")
        await bot.reply_to(message, f"{EMOJI['banned']} شما چت را قطع کردید. برای شروع مجدد دکمه 🎲 رو بزنید.", reply_markup=kb_main)
        
        if partner_id:
            p_code = await get_or_create_short_link(partner_id)
            u_code = await get_or_create_short_link(user_id)
            
            markup_user = InlineKeyboardMarkup().row(
                InlineKeyboardButton(text=f"{EMOJI['ok']} لایک (+۱ سکه)", callback_data=f"rate_like_{p_code}"),
                InlineKeyboardButton(text=f"{EMOJI['ban']} دیس‌لایک و بلاک (+۱ سکه)", callback_data=f"rate_dis_{p_code}")
            )
            await bot.send_message(user_id, f"{EMOJI['qe']} <b>کیفیت چت چطور بود؟</b>\nبه پارتنرت امتیاز بده (با ثبت امتیاز، ۱ سکه رایگان از ربات جایزه بگیر!):", parse_mode="HTML", reply_markup=markup_user)
            
            markup_partner = InlineKeyboardMarkup().row(
                InlineKeyboardButton(text=f"{EMOJI['ok']} لایک (+۱ سکه)", callback_data=f"rate_like_{u_code}"),
                InlineKeyboardButton(text=f"{EMOJI['ban']} دیس‌لایک و بلاک (+۱ سکه)", callback_data=f"rate_dis_{u_code}")
            )
            
            try:
                await bot.send_message(partner_id, f"{EMOJI['caution']} <b>پارتنر شما چت را قطع کرد.</b>\n{EMOJI['qe']} کیفیت چت چطور بود؟ بهش امتیاز بده (+۱ سکه هدیه):", parse_mode="HTML", reply_markup=kb_main)
                await bot.send_message(partner_id, f"{EMOJI['up']} لطفاً امتیاز خود به پارتنر سابق را در کادر بالا ثبت کنید.", reply_markup=markup_partner)
            except Exception: pass

    # ==========================================
    # ⭐ کالبک‌های سیستم امتیازدهی و بلاک چت تصادفی
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("rate_"))
    async def handle_rating_callbacks(call):
        action = call.data.split("_")[1]  
        partner_code = call.data.split("_")[-1]
        partner_id = await get_user_id_by_short_code(partner_code)
        user_id = call.message.chat.id
        
        if not partner_id:
            await bot.answer_callback_query(call.id, "❌ خطای فنی در ثبت امتیاز.")
            return
            
        if action == "like":
            await submit_user_rating(partner_id, is_like=True, voter_id=user_id)
            await send_bot_log(bot, call.message, "ثبت امتیاز لایک", f"به پارتنر سابق: {partner_id}")
            await bot.answer_callback_query(call.id, "ثبت شد و ۱ سکه هدیه گرفتی! 👍", show_alert=True)
            await bot.edit_message_text(f"{EMOJI['crcl_yes']} مرسی! بازخورد مثبتت ثبت شد و حساب شما شارژ گردید.", user_id, call.message.message_id)
        elif action == "dis":
            await submit_user_rating(partner_id, is_like=False, voter_id=user_id)
            await add_to_chat_history_match(user_id, partner_id, "dislike")
            await send_bot_log(bot, call.message, "ثبت امتیاز دیس‌لایک و بلاک چت تصادفی", f"پارتنر مسدود شده: {partner_id}")
            await bot.answer_callback_query(call.id, "ثبت و بلاک شد و ۱ سکه هدیه گرفتی! 🛑", show_alert=True)
            await bot.edit_message_text(f"{EMOJI['banned']} ثبت شد. این کاربر وارد لیست سیاه چت تصادفی شما شد و ۱ سکه هدیه دریافت کردی.", user_id, call.message.message_id)