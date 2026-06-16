import time
import asyncio
import traceback
import json
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# وارد کردن توابع پایه دیتابیس مورد نیاز برای بخش ناشناس
from src.database.db_manager import (
    register_or_update_user, set_user_state, save_message_mapping, 
    get_anon_sender_by_msg, block_user, is_user_blocked, get_super_user_by_msg, 
    get_user_chat_status_ext, set_user_referrer, get_or_create_short_link, 
    get_user_id_by_short_code, get_complete_user_context, get_user_id_by_username,
    try_matchmaking, connect_two_users, leave_random_chat_queue, apply_queue_compensation,
    get_user_profile_stats
)

# دریافت تمام ابزارهای ردیس، کش و لاگر متمرکز از فایل خنثی
from src.config import EMOJI
from src.bot.redis_config import redis_client, log_queue, cache_set_user_context, cache_invalidate_user, send_bot_log

GOD_ID = 6779908406
LOG_GROUP_ID = -5295499371

# ==========================================
# ⌨️ بخش اول: مدیریت کیبوردهای اصلی ربات (Reply Keyboards)
# ==========================================
def get_keyboards():
    from telebot.types import ReplyKeyboardMarkup, KeyboardButton
    main = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main.add(KeyboardButton("🎲 شروع چت تصادفی"), KeyboardButton("📊 آمار من"))
    main.row(KeyboardButton("🔍 ارسال پیام ناشناس به آیدی خاص"))
    main.add(KeyboardButton("💰 سکه‌های من"), KeyboardButton("❌ حذف کامل اطلاعات من"))
    main.row(KeyboardButton("🗑️ خالی کردن لیست سیاه"))
    
    search = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    search.add(KeyboardButton("❌ انصراف از صف جستجو"))
    
    chatting = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    chatting.add(KeyboardButton("🛑 قطع چت فعال"))
    return main, search, chatting


def register_private_anon_handlers(bot: AsyncTeleBot):

    # ==========================================
    # ⚙️ بخش دوم: هندلر دستور /start مجهز به تفکیک قطعی فلو تبلیغات و ناشناس
    # ==========================================
    @bot.message_handler(commands=['start'])
    async def handle_start(message):
        if message.chat.type != "private": return
        bot_info = await bot.get_me()
        command_args = message.text.split()
        user_id = message.chat.id
        first_name = message.from_user.first_name or "دوست"
        
        await cache_invalidate_user(user_id)
        context = await get_complete_user_context(user_id)
        is_new_user = context.get("short_code") is None
        
        await register_or_update_user(user_id, first_name, message.from_user.username)
        kb_main, _, _ = get_keyboards()
        
        if len(command_args) > 1:
            command_arg_val = command_args[1]
            if command_arg_val.startswith("ad_"):
                if is_new_user:
                    channel_name = command_arg_val.split("ad_")[-1]
                    await send_bot_log(bot, message, "📥 ورود از کمپین تبلیغاتی", f"کاربر جدید از لینک کانال [{channel_name}] وارد شد 🔥")
            else:
                short_code = command_arg_val
                target_owner_id = await get_user_id_by_short_code(short_code)
                if target_owner_id and user_id != target_owner_id:
                    if await is_user_blocked(owner_id=target_owner_id, blocked_id=user_id):
                        # 🔧 اضافه شدن پارامتر parse_mode برای لود صحیح اموجی بلاک
                        await bot.reply_to(message, f"{EMOJI['ban']['html']} شما توسط این کاربر بلاک شده‌اید.", parse_mode="HTML", reply_markup=kb_main)
                        return
                    
                    await set_user_referrer(user_id, target_owner_id, is_pure_ref=is_new_user)
                    await cache_invalidate_user(target_owner_id)
                    
                    if is_new_user:
                        try:
                            await bot.send_message(target_owner_id, f"{EMOJI['qe']['html']} <b>یک عضو جدید با لینک شما وارد شد!</b>\n{EMOJI['profile']['html']} دوست شما <b>{first_name}</b> وارد ربات شد. به محض استارت چت تصادفی، ۵ سکه هدیه می‌گیری!", parse_mode="HTML")
                        except Exception: pass
                        ref_welcome = f"{EMOJI['sus']['html']} <b>خوش اومدی!</b>\n\nشما با لینک معرف وارد شدی و حسابت با <b>۱۵ سکه اولیه</b> شارژ شد! {EMOJI['present']['html']}"
                        await bot.reply_to(message, ref_welcome, parse_mode="HTML", reply_markup=kb_main)
                    
                    await set_user_state(user_id, f"sending_anon_to_{short_code}")
                    await send_bot_log(bot, message, "کامند /start", f"کلیک روی لینک کوتاه کاربر: {target_owner_id}")
                    await bot.reply_to(message, f"{EMOJI['mail']['html']} در حال ارسال پیام ناشناس... مدیا یا متن خود را بفرستید:", parse_mode="HTML", reply_markup=kb_main)
                    return
        
        my_short_code = await get_or_create_short_link(user_id)
        anon_link = f"https://t.me/{bot_info.username}?start={my_short_code}"
        
        if len(command_args) <= 1 or not command_args[1].startswith("ad_"):
            await send_bot_log(bot, message, "کامند /start", f"استارت معمولی و دریافت لینک کوتاه: {my_short_code}")
        
        # 💎 دکمه‌های شیشه‌ای استارت با کاراکتر واقعی برای لود متحرک بدون کد خام HTML
        inline_kb = InlineKeyboardMarkup()
        inline_kb.row(InlineKeyboardButton(text=f"{EMOJI['link']['char']} دریافت بنر استوری و لینک من", callback_data=f"get_my_banner_{my_short_code}"))
        inline_kb.row(InlineKeyboardButton(text=f"{EMOJI['shield']['char']} چرا این ربات ۱۰۰٪ امن و مخفی است؟", callback_data="bot_security_info"))

        god_text = f"سلام و درود فرشته عزیز. 🙇‍♂️\nهوش مصنوعی گوش به فرمان شماست.\n───\n{EMOJI['link']['html']} <b>لینک ناشناس شما:</b>\n{anon_link}"
        normal_text = f"{EMOJI['sus']['html']} <b>به ربات پیام ناشناس CyberAnons خوش آمدید!</b>\n\n{EMOJI['link']['html']} <b>لینک اختصاصی شما:</b>\n<code>{anon_link}</code>"
        
        msg = god_text if user_id == GOD_ID else normal_text
        await bot.reply_to(message, msg, parse_mode="HTML", reply_markup=inline_kb)
        await bot.send_message(user_id, f"چه کاری می‌تونم برات انجام بدم؟ {EMOJI['thunder']['html']}", reply_markup=kb_main, parse_mode="HTML")

    # ==========================================
    # 🔥 بخش سوم: هندلر دکمه‌های شیشه‌ای (Callback Query Handler)
    # ==========================================
    @bot.callback_query_handler(func=lambda call: True)
    async def handle_callback_queries(call):
        user_id = call.message.chat.id
        kb_main, _, _ = get_keyboards()
        
        # ۱. دکمه شیشه‌ای امنیت ربات
        if call.data == "bot_security_info":
            security_text = (
                f"{EMOJI['shield']['html']} <b>چرا ربات CyberAnons ۱۰۰٪ امن و ناشناس است؟</b>\n\n"
                f"{EMOJI['one']['html']} <b>عدم ذخیره اطلاعات هویتی:</b> پیام‌های شما در دیتابیس به صورت رمزنگاری‌شده عبور می‌کنند و آیدی عددی شما به هیچ‌وجه برای پارتنر یا گیرنده پیام ناشناس فاش نخواهد شد.\n\n"
                f"{EMOJI['two']['html']} <b>سیستم خودکار اتمیک:</b> مچ‌میکینگ و تبادل پیام‌ها کاملاً توسط سرور و هوش مصنوعی و بدون دخالت انسان انجام می‌شود.\n\n"
                f"{EMOJI['three']['html']} <b>لایه امنیتی ضدتخریب (Anti-Troll):</b> کاربران مزاحم به سرعت توسط سیستم ریتینگ مسدود می‌شوند تا محیطی امن برای شما فراهم شود.\n\n"
                f"با خیال راحت ناشناس بمانید! {EMOJI['secret']['html']}"
            )
            try:
                await bot.send_message(user_id, security_text, parse_mode="HTML", reply_markup=kb_main)
                await bot.answer_callback_query(call.id, "اطلاعات امنیتی با موفقیت بارگذاری شد.")
            except Exception: pass
            return

        # ۲. هندلر دکمه شیشه‌ای بنر استوری و رفرال
        if call.data.startswith("get_my_banner_"):
            try:
                first_name = call.from_user.first_name or "دوست"
                short_code = call.data.split("get_my_banner_")[-1]
                bot_info = await bot.get_me()
                anon_link = f"https://t.me/{bot_info.username}?start={short_code}"
                
                banner_text = (
                    f"سلام {first_name} هستم 😉\n"
                    f"لینک زیر رو لمس کن و هر انتقادی که نسبت به من داری یا حرفی که تو دلت هست رو با خیال راحت بنویس و بفرست. "
                    f"بدون اینکه از اسمت باخبر بشم پیامت به من می‌رسه. "
                    f"خودتم می‌تونی امتحان کنی و از همه بخوای راحت و ناشناس بهت پیام بفرستن، حرفای خیلی جالبی می‌شنوی:\n\n"
                    f"👉 {anon_link}"
                )
                
                await bot.send_message(user_id, banner_text)
                await bot.answer_callback_query(call.id, "✅ بنر شما با موفقیت ارسال شد!")
            except Exception as e:
                print(f"💥 Error in sending banner: {e}")
                await bot.answer_callback_query(call.id, "❌ خطایی در ساخت بنر رخ داد.")
            return

        # ۳. پاسخ ناشناس از طریق دکمه شیشه‌ای پاسخ دایرکت
        if call.data.startswith("reply_to_"):
            short_code = call.data.split("reply_to_")[-1]
            await set_user_state(user_id, f"sending_anon_to_{short_code}")
            await cache_invalidate_user(user_id)
            await bot.send_message(user_id, f"{EMOJI['right']['html']} <b>پاسخ خود را بنویسید یا مدیا (عکس، وویس و...) بفرستید:</b>", parse_mode="HTML")
            await bot.answer_callback_query(call.id)
            return

        # ۴. بلاک کردن کاربر از طریق دکمه شیشه‌ای بلاک دایرکت
        if call.data.startswith("block_"):
            short_code = call.data.split("block_")[-1]
            target_id = await get_user_id_by_short_code(short_code)
            if target_id:
                await block_user(owner_id=user_id, blocked_id=target_id)
                # 🔧 اضافه شدن پارامتر parse_mode برای رندر صحیح لایو اموجی مسدودکننده
                await bot.send_message(user_id, f"{EMOJI['banned']['html']} کاربر با موفقیت در لیست سیاه شما قرار گرفت و دیگر نمی‌تواند به شما پیام بدهد.", parse_mode="HTML")
                await bot.answer_callback_query(call.id, "کاربر مسدود شد.")
            return

    # ==========================================
    # 🔍 هندلر دکمه ارسال پیام ناشناس به آیدی خاص
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "🔍 ارسال پیام ناشناس به آیدی خاص" and m.chat.type == "private")
    async def handle_send_by_username(message):
        user_id = message.chat.id
        await send_bot_log(bot, message, "دکمه 🔍 ارسال پیام ناشناس به آیدی خاص")
        await set_user_state(user_id, "waiting_for_username")
        await cache_invalidate_user(user_id)
        await bot.reply_to(message, f"{EMOJI['magnifiyer']['html']} <b>آیدی تلگرام (Username) شخص مورد نظرت رو بفرست:</b>", parse_mode="HTML")

    # ==========================================
    # 👑 هندلر جامع تونل‌زنی زنده پیام‌ها و پاسخ‌های ناشناس پیوی
    # ==========================================
    @bot.message_handler(
        content_types=['text', 'photo', 'video', 'voice', 'audio', 'sticker', 'animation'], 
        func=lambda m: m.chat.type == "private" and (m.text is None or not m.text.startswith('/')) and m.text not in [
            "📊 آمار من", "🎲 شروع چت تصادفی", "❌ انصراف از صف جستجو", "🛑 قطع چت فعال", 
            "💰 سکه‌های من", "🔍 ارسال پیام ناشناس به آیدی خاص", "❌ حذف کامل اطلاعات من", "🗑️ خالی کردن لیست سیاه"
        ]
    )
    async def handle_private_anon_flow(message):
        user_id = message.chat.id
        context = None
        if redis_client:
            try:
                cached_data = await redis_client.get(f"user_ctx:{user_id}")
                if cached_data: context = json.loads(cached_data)
            except Exception: pass
            
        if not context:
            context = await get_complete_user_context(user_id)
            await cache_set_user_context(user_id, context, ttl=1800)
        
        status = context.get("chat_status")
        partner_id = context.get("active_partner_id")
        current_state = context.get("anon_state", "normal")
        reply_target_id = context.get("reply_target_id")
        sender_short_code = context.get("short_code")
        
        if not sender_short_code:
            sender_short_code = await get_or_create_short_link(user_id)
            await cache_invalidate_user(user_id)
        
        # چت تصادفی فعال
        if status == 'chatting' and partner_id:
            try:
                await bot.copy_message(chat_id=partner_id, from_chat_id=user_id, message_id=message.message_id)
            except Exception:
                from src.bot.handlers.random_chat import disconnect_active_chat
                await disconnect_active_chat(user_id)
                await cache_invalidate_user(user_id)
                await cache_invalidate_user(partner_id)
                kb_main, _, _ = get_keyboards()
                # 🔧 اضافه شدن پارامتر parse_mode برای لود صحیح اموجی خطا در قطع چت
                await bot.send_message(user_id, f"{EMOJI['crcl_no']['html']} ارتباط قطع شد؛ پارتنر ربات رو بلاک کرده است.", parse_mode="HTML", reply_markup=kb_main)
            return

        # حالت انتظار برای دریافت یوزرنیم مقصد
        if current_state == "waiting_for_username":
            if not message.text or message.text.startswith('/'): return
            target_username = message.text.strip().replace("@", "")
            target_id = await get_user_id_by_username(target_username)
            if not target_id:
                await bot.reply_to(message, f"{EMOJI['crcl_no']['html']} کاربری با این آیدی در ربات پیدا نشد!", parse_mode="HTML")
                await set_user_state(user_id, "normal")
                await cache_invalidate_user(user_id)
                return
            if target_id == user_id:
                await bot.reply_to(message, f"{EMOJI['caution']['html']} نمی‌توانی به خودت پیام ناشناس بفرستی!", parse_mode="HTML")
                return
            target_short_code = await get_or_create_short_link(target_id)
            await set_user_state(user_id, f"sending_anon_to_{target_short_code}")
            await cache_invalidate_user(user_id)
            await bot.reply_to(message, f"{EMOJI['link']['html']} ارتباط برقرار شد! متن یا رسانه خود را ارسال کنید:", parse_mode="HTML")
            return

        help_guide_text = f"\n\n{EMOJI['light']['html']} <b>راهنما:</b> برای جواب دادن روی دکمهٔ {EMOJI['right']['html']} <b>پاسخ</b> کلیک کنید یا روی پیام <b>Reply</b> کنید."

        # پاسخ مستقیم با ریپلای تلگرام
        if message.reply_to_message:
            mapping = await get_anon_sender_by_msg(user_id, message.reply_to_message.message_id) or await get_super_user_by_msg(user_id, message.reply_to_message.message_id)
            if mapping:
                anon_sender_id, anon_msg_id = mapping
                
                # 💎 دکمه شیشه‌ای با کاراکتر متحرک واقعی بدون کدهای خراب HTML
                markup = InlineKeyboardMarkup().row(
                    InlineKeyboardButton(text=f"{EMOJI['right']['char']} پاسخ", callback_data=f"reply_to_{sender_short_code}"), 
                    InlineKeyboardButton(text=f"{EMOJI['banned']['char']} بلاک", callback_data=f"block_{sender_short_code}")
                )
                if message.content_type == 'text':
                    sent = await bot.send_message(anon_sender_id, f"{EMOJI['mail']['html']} پاسخ ناشناس شما:\n\n« {message.text} »{help_guide_text}", reply_to_message_id=anon_msg_id, reply_markup=markup, parse_mode="HTML")
                else:
                    sent = await bot.copy_message(chat_id=anon_sender_id, from_chat_id=user_id, message_id=message.message_id, reply_to_message_id=anon_msg_id, reply_markup=markup)
                    await bot.send_message(chat_id=anon_sender_id, text=f"{EMOJI['up']['html']} پاسخ رسانه‌ای ناشناس بالا دریافت شد.{help_guide_text}", reply_to_message_id=sent.message_id, reply_markup=markup, parse_mode="HTML")
                
                await send_bot_log(bot, message, "ارسال پاسخ ناشناس پیوی")
                await save_message_mapping(anon_sender_id, sent.message_id, user_id, message.message_id)
                await bot.reply_to(message, f"{EMOJI['thunder']['html']} فرستاده شد.", parse_mode="HTML")
            return

        # ارسال پیام ناشناس به کد ۸ رقمی مقصد
        if current_state.startswith("sending_anon_to_"):
            short_code = current_state.split("sending_anon_to_")[-1]
            target_id = await get_user_id_by_short_code(short_code)
            if not target_id:
                await bot.reply_to(message, f"{EMOJI['crcl_no']['html']} این لینک معتبر نیست.", parse_mode="HTML")
                await set_user_state(user_id, "normal")
                await cache_invalidate_user(user_id)
                return
                
            markup = InlineKeyboardMarkup().row(
                InlineKeyboardButton(text=f"{EMOJI['right']['char']} پاسخ", callback_data=f"reply_to_{sender_short_code}"), 
                InlineKeyboardButton(text=f"{EMOJI['banned']['char']} بلاک", callback_data=f"block_{sender_short_code}")
            )
            god_intel = f"{EMOJI['eyes']['html']} <b>فرستنده برای فرشته:</b>\n👤 {message.from_user.first_name}\n🆔 @{message.from_user.username or 'No'}\n───\n\n" if target_id == GOD_ID else ""
            try:
                if message.content_type == 'text': 
                    sent_msg = await bot.send_message(target_id, f"{god_intel}{EMOJI['mail']['html']} پیام ناشناس جدید:\n💬 <code>{message.text}</code>{help_guide_text}", reply_markup=markup, parse_mode="HTML")
                else: 
                    sent_msg = await bot.copy_message(chat_id=target_id, from_chat_id=user_id, message_id=message.message_id, caption=f"{god_intel}{EMOJI['mail']['html']} پیام ناشناس جدید\n" + (message.caption or ""), parse_mode="HTML")
                    await bot.send_message(chat_id=target_id, text=f"{EMOJI['up']['html']} پیام رسانه‌ای بالا دریافت شد.{help_guide_text}", reply_to_message_id=sent_msg.message_id, reply_markup=markup, parse_mode="HTML")
                
                if sent_msg:
                    await send_bot_log(bot, message, "ارسال پیام ناشناس")
                    await bot.reply_to(message, f"{EMOJI['crcl_yes']['html']} مخفیانه ارسال شد.", parse_mode="HTML")
                    await save_message_mapping(target_id, sent_msg.message_id, user_id, message.message_id)
            except Exception:
                await bot.reply_to(message, f"{EMOJI['crcl_no']['html']} خطا در ارسال پیام. مقصد شما را مسدود کرده است.", parse_mode="HTML")
            
            await set_user_state(user_id, "normal")
            await cache_invalidate_user(user_id)
            return

        # پاسخ متوالی در استیت قفل ماشین وضعیت (Replying Mode)
        if current_state == "replying_mode" and reply_target_id:
            markup = InlineKeyboardMarkup().row(
                InlineKeyboardButton(text=f"{EMOJI['right']['char']} پاسخ", callback_data=f"reply_to_{sender_short_code}"), 
                InlineKeyboardButton(text=f"{EMOJI['banned']['char']} بلاک", callback_data=f"block_{sender_short_code}")
            )
            try:
                if message.content_type == 'text':
                    sent = await bot.send_message(reply_target_id, f"{EMOJI['mail']['html']} پاسخ ناشناس جدید:\n\n« {message.text} »{help_guide_text}", reply_markup=markup, parse_mode="HTML")
                else:
                    sent = await bot.copy_message(chat_id=reply_target_id, from_chat_id=user_id, message_id=message.message_id)
                    await bot.send_message(chat_id=reply_target_id, text=f"{EMOJI['up']['html']} پاسخ رسانه‌ای جدید دریافت شد.{help_guide_text}", reply_to_message_id=sent.message_id, reply_markup=markup, parse_mode="HTML")
                await save_message_mapping(reply_target_id, sent.message_id, user_id, message.message_id)
                await bot.reply_to(message, f"{EMOJI['thunder']} فرستاده شد.", parse_mode="HTML")
            except Exception:
                await bot.reply_to(message, f"{EMOJI['crcl_no']['html']} ارسال پاسخ انجام نشد.", parse_mode="HTML")
            
            await set_user_state(user_id, "normal")
            await cache_invalidate_user(user_id)
            return