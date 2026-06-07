import re
import asyncio
import traceback
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from src.utils.crypto import encode_user_id, decode_user_id
from src.database.db_manager import (
    register_or_update_user, get_user_state, set_user_state, clear_user_state,
    save_message_mapping, get_anon_sender_by_msg, block_user, is_user_blocked, 
    get_super_user_by_msg, get_user_profile_stats,
    get_user_chat_status_ext, join_random_chat_queue, leave_random_chat_queue,
    try_matchmaking, connect_two_users, disconnect_active_chat, apply_queue_compensation,
    set_user_referrer, submit_user_rating, add_to_chat_history_match, update_user_gender,
    get_or_create_short_link, get_user_id_by_short_code, get_complete_user_context,
    get_user_id_by_username
)

GOD_ID = 6779908406
LOG_GROUP_ID = -5295499371

# ==========================================
# ⚡ بخش ویژه: تابع مرکزی ارسال لاگ به گروه (Central Logger)
# ==========================================
async def send_bot_log(bot: AsyncTeleBot, message, action_name: str, extra_details: str = ""):
    """ارسال زنده و خودکار گزارش عملکرد کاربران به گروه لاگ اختصاصی"""
    try:
        user = message.from_user
        if user.id == 8627765327:
            return
        log_text = (
            f"📥 <b>[LOG] فعالیت جدید در ربات</b>\n"
            f"👤 <b>کاربر:</b> {user.first_name}\n"
            f"🪪 <b>آیدی عددی:</b> <code>{message.chat.id}</code>\n"
            f"🆔 <b>یوزرنیم:</b> @{user.username or 'No_Username'}\n"
            f"🛠 <b>اکشن:</b> <code>{action_name}</code>\n"
        )
        if extra_details:
            log_text += f"📝 <b>جزئیات:</b> {extra_details}\n"
            
        await bot.send_message(LOG_GROUP_ID, log_text, parse_mode="HTML")
    except Exception as e:
        print(f"💥 Line logger failed to send to group: {e}")

# ==========================================
# ⌨️ بخش اول: مدیریت کیبوردهای اصلی ربات (Reply Keyboards)
# ==========================================
def get_keyboards():
    """تولید داینامیک منوهای اصلی ربات برای هدایت راحت کاربر در مراحل مختلف"""
    main = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main.add(KeyboardButton("🎲 شروع چت تصادفی"), KeyboardButton("📊 آمار من"))
    
    # قرار گرفتن دکمه ارسال به آیدی خاص در یک ردیف اختصاصی و عریض
    main.row(KeyboardButton("🔍 ارسال پیام ناشناس به آیدی خاص"))
    
    main.add(KeyboardButton("💰 سکه‌های من"))
    
    search = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    search.add(KeyboardButton("❌ انصراف از صف جستجو"))
    
    chatting = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    chatting.add(KeyboardButton("🛑 قطع چت فعال"))
    
    return main, search, chatting


def register_private_anon_handlers(bot: AsyncTeleBot):

    # ==========================================
    # ⚙️ بخش دوم: هندلر دستور /start مجهز به سیستم رفرال و رادار تبلیغات فوق‌کوتاه
    # ==========================================
    @bot.message_handler(commands=['start'])
    async def handle_start(message):
        """مدیریت استارت اولیه، رفرال، رادار کمپین‌های تبلیغاتی و پیام ناشناس متمرکز با کدهای کوتاه"""
        if message.chat.type != "private": return
        bot_info = await bot.get_me()
        command_args = message.text.split()
        user_id = message.chat.id
        first_name = message.from_user.first_name or "دوست"
        
        # بررسی وضعیت ثبت‌نام پیشین کاربر برای تشخیص سیستم رفرال
        context = await get_complete_user_context(user_id)
        is_new_user = context["short_code"] is None
        
        await register_or_update_user(user_id, first_name, message.from_user.username)
        kb_main, _, _ = get_keyboards()
        
        # پردازش آرگومان ورودی لینک استارت
        if len(command_args) > 1:
            argument = command_args[1]
            
            # 📢 لایه اول: رادار ردیابی کمپین‌های تبلیغاتی (مثال: ?start=ad_ecstasy)
            if argument.startswith("ad_") and is_new_user:
                channel_name = argument.split("ad_")[-1]
                # ارسال لاگ هوشمند به گروه بدون استفاده از return جهت جلوگیری از قفل شدن ربات
                await send_bot_log(
                    bot, 
                    message, 
                    "📥 ورود از کمپین تبلیغاتی", 
                    f"کاربر جدید از لینک تبلیغاتی کانال [{channel_name}] وارد شد 🔥"
                )
            
            # 🔗 لایه دوم: پردازش رفرال و هدایت به پیام ناشناس دیتابیسی ۸ کاراکتری
            else:
                short_code = argument
                target_owner_id = await get_user_id_by_short_code(short_code)
                
                if target_owner_id and user_id != target_owner_id:
                    if await is_user_blocked(owner_id=target_owner_id, blocked_id=user_id):
                        await bot.reply_to(message, "❌ شما توسط این کاربر بلاک شده‌اید.", reply_markup=kb_main)
                        return
                    
                    # ثبت رفرال هوشمند متمرکز (کاربر جدید پاداش ۱۵ سکه می‌گیرد)
                    await set_user_referrer(user_id, target_owner_id, is_pure_ref=is_new_user)
                    
                    if is_new_user:
                        try:
                            await bot.send_message(
                                chat_id=target_owner_id, 
                                text=f"🔔 <b>یک عضو جدید با لینک شما وارد شد!</b>\n👤 دوست شما <b>{first_name}</b> وارد ربات شد. به محض اینکه اولین 🎲 <b>چت تصادفی</b> خودش رو استارت بزنه، ۵ سکه هدیه به حسابت واریز میشه!",
                                parse_mode="HTML"
                            )
                        except Exception: pass
                            
                        ref_welcome = (
                            f"👋 <b>خوش اومدی!</b>\n\n"
                            f"شما با لینک یکی از دوستانتان وارد ربات شده‌اید.\n"
                            f"🎁 به پاس احترام، حساب شما با <b>۱۵ سکه اولیه</b> (بجای ۱۰ سکه) شارژ شد! همچنین به محض اینکه اولین 🎲 <b>چت تصادفی</b> خود را استارت بزنید، <b>۵ سکه رایگان</b> هم به معرف شما هدیه داده می‌شود.\n\n"
                            f"الآن می‌توانید از منوی زیر استفاده کنید:"
                        )
                        await bot.reply_to(message, ref_welcome, parse_mode="HTML", reply_markup=kb_main)
                    
                    # هدایت مستقیم کاربر به وضعیت ارسال پیام ناشناس به صاحب لینک
                    await set_user_state(user_id, f"sending_anon_to_{short_code}")
                    await send_bot_log(bot, message, "کامند /start", f"کلیک روی لینک کوتاه کاربر: {target_owner_id} (کد: {short_code})")
                    await bot.reply_to(message, "📥 در حال ارسال پیام ناشناس... مدیا یا متن خود را بفرستید:", reply_markup=kb_main)
                    return
        
        # جریان عادی ربات در صورت استارت معمولی یا عبور بدون قطع ریکوئست از رادار تبلیغات ad_
        my_short_code = await get_or_create_short_link(user_id)
        anon_link = f"https://t.me/{bot_info.username}?start={my_short_code}"
        await send_bot_log(bot, message, "کامند /start", f"استارت معمولی و دریافت لینک کوتاه: {my_short_code}")
        
        inline_kb = InlineKeyboardMarkup()
        inline_kb.add(InlineKeyboardButton("🔗 دریافت بنر استوری و لینک من", callback_data=f"get_my_banner_{my_short_code}"))

        god_text = f"سلام و درود ارباب فاطمه. 🙇‍♂️\nهوش مصنوعی گوش به فرمان شماست.\n\n👁️‍🗨️ <b>دسترسی ارشد ویژه:</b>\nشما برخلاف کاربران عادی, توانایی مشاهدهٔ اطلاعات دقیق فرستندهٔ پیام‌ها را دارید.\n\n🔗 <b>لینک ناشناس ارباب:</b>\n{anon_link}"
        
        normal_text = (
            f"👋 <b>به ربات پیام ناشناس CyberAnons خوش آمدید!</b>\n\n"
            f"اینجا یک فضای کاملاً امن، مخفی و پرسرعت برای گفتگوست 🕶️\n\n"
            f"🔗 <b>لینک اختصاصی شما:</b>\n<code>{anon_link}</code>\n\n"
            f"👇 با دکمهٔ زیر می‌توانید بنر آماده شدهٔ این لینک را برای قرار دادنใน استوری اینستاگرام یا کانال تلگرامتان دریافت کنید:"
        )
        
        msg = god_text if user_id == GOD_ID else normal_text
        await bot.reply_to(message, msg, parse_mode="HTML", reply_markup=inline_kb)
        await bot.send_message(user_id, "چه کاری می‌تونم برات انجام بدم؟ 🕶️✨", reply_markup=kb_main)

    # ==========================================
    # 🔗 هندلر کالبک دکمه شیشه‌ای ارسال بنر آماده استوری
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("get_my_banner_"))
    async def handle_get_my_banner(call):
        try:
            user_id = call.message.chat.id
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


    # ==========================================
    # 🔍 هندلر دکمه ارسال پیام ناشناس به آیدی خاص
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "🔍 ارسال پیام ناشناس به آیدی خاص" and m.chat.type == "private")
    async def handle_send_by_username(message):
        user_id = message.chat.id
        await send_bot_log(bot, message, "دکمه 🔍 ارسال پیام ناشناس به آیدی خاص")
        
        # تغییر وضعیت ماشین وضعیت کاربر به انتظار برای دریافت یوزرنیم
        await set_user_state(user_id, "waiting_for_username")
        
        prompt_text = (
            "🕶️ <b>آیدی تلگرام (Username) شخص مورد نظرت رو بفرست:</b>\n\n"
            "⚠️ <b>نکته:</b> آیدی رو می‌تونی با @ یا بدون @ بفرستی. "
            "فقط حواست باشه اون شخص باید حداقل یک‌بار این ربات رو استارت کرده باشه تا سیستم ما بتونه پیداش کنه."
        )
        
        await bot.reply_to(message, prompt_text, parse_mode="HTML")


    # ==========================================
    # 📊 بخش سوم: مدیریت پروفایل و آمار من (Profile Stats)
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "📊 آمار من" and m.chat.type == "private")
    async def handle_my_stats(message):
        await send_bot_log(bot, message, "دکمه 📊 آمار من")
        stats = await get_user_profile_stats(message.chat.id)
        gender_map = {"male": "🙋‍♂️ پسر", "female": "🙋‍♀️ دختر", None: "ثبت نشده ⚠️"}
        
        # 🎯 اضافه شدن فلو نمایش ناشناس ارسال شده (stats['sent']) به خروجی نهایی
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
    # 💰 بخش چهارم: مدیریت کیف پول سکه و راهنمای ربات
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "💰 سکه‌های من" and m.chat.type == "private")
    async def handle_my_coins(message):
        await send_bot_log(bot, message, "دکمه 💰 سکه‌های من")
        user_id = message.chat.id
        stats = await get_user_profile_stats(user_id)
        inline_kb = InlineKeyboardMarkup()
        inline_kb.add(InlineKeyboardButton("📜 راهنمای کسب سکه رایگان", callback_data="coin_help"))
        response_text = (
            f"<b>💰 مدیریت کیف پول سکه</b>\n\n"
            f"👤 | کاربر: {message.from_user.first_name}\n"
            f"🪙 | موجودی فعلی شما: <b>{stats['coins']} سکه</b>\n\n"
            f"⚡ با سکه‌های خود می‌توانید در بخش 🎲 <b>چت تصادفی</b> به پارتنرهای هم‌سطح متصل شوید!"
        )
        await bot.reply_to(message, response_text, parse_mode="HTML", reply_markup=inline_kb)

    @bot.callback_query_handler(func=lambda c: c.data == "coin_help")
    async def handle_coin_help_callback(call):
        await send_bot_log(bot, call.message, "کالبک شیشه‌ای coin_help", "باز کردن راهنمای جامع اقتصاد ربات")
        user_id = call.message.chat.id
        bot_info = await bot.get_me()
        
        # بهینه‌سازی: استفاده از همان لینک ناشناس فوق‌کوتاه برای سیستم دعوت رفرال کاربری
        my_short_code = await get_or_create_short_link(user_id)
        ref_link = f"https://t.me/{bot_info.username}?start={my_short_code}"  
        
        help_text = (
            f"<b>📜 راهنمای جامع سیستم اقتصاد سکه</b>\n\n"
            f"🪙 <b>سکه چیست؟</b>\n"
            f"واحد مالی ربات برای برقراری اتصال در چت تصادفی است.\n\n"
            f"🚀 <b>راه‌های کسب سکه رایگان:</b>\n\n"
            f"۱. <b>استارت اولیه:</b> هر کاربر در عادی‌ترین حالت ورود <b>۱۰ سکه رایگان</b> هدیه می‌گیرد.\n\n"
            f"۲. <b>سیستم رفرال (دعوت دوستان):</b> این لینک اختصاصی شماست:\n"
            f"<code>{ref_link}</code>\n\n"
            f"اگر کسی با لینک بالا عضو ربات شود، حساب خودش پاداش گرفته و با <b>۱۵ سکه اولیه</b> استارت می‌زند! همچنین به محض اینکه اولین 🎲 چت تصادفی خودش را شروع کند، <b>۵ سکه رایگان</b> به عنوان پاداش به حساب شما واریز می‌شود!\n\n"
            f"💡 <b>یک تیر و دو نشان:</b> لینک ناشناس و لینک دعوت شما کاملاً یکسان هستند! دوستانتان هم می‌توانند به شما پیام ناشناس بفرستند و همزمان اگر قبلاً عضو ربات نبوده باشند، زیرمجموعهٔ شما ثبت خواهند شد.\n\n"
            f"۳. <b>جریمه معطلی ربات:</b> اگر در صف جستجو وارد شوید و به دلیل شلوغی تا ۱۵ دقیقه پارتنری برای شما پیدا نشد، ۲ سکه رایگان هم به عنوان جریمه از طرف ربات دریافت می‌کنید! (دارای کول‌داون ۳ ساعته)"
        )
        await bot.send_message(user_id, help_text, parse_mode="HTML")
        await bot.answer_callback_query(call.id)


    # ==========================================
    # 🎲 بخش پنجم: موتور اصلی مچ‌میکینگ لایو و رادار انحصاری ارباب فاطمه
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "🎲 شروع چت تصادفی" and m.chat.type == "private")
    async def handle_start_random_chat(message):
        user_id = message.chat.id
        status, _, coins, gender = await get_user_chat_status_ext(user_id)
        kb_main, kb_search, kb_chatting = get_keyboards()
        
        if status == 'chatting':
            await bot.reply_to(message, "⚠️ شما در یک چت فعال هستید! اول باید با دکمه زیر چت قبلی رو قطع کنی.", reply_markup=kb_chatting)
            return
        if status == 'searching':
            await bot.reply_to(message, "🔍 شما در صف جستجو هستید...", reply_markup=kb_search)
            return

        if not gender:
            markup_gender = InlineKeyboardMarkup().row(
                InlineKeyboardButton("🙋‍♂️ پسرم", callback_data="set_gender_male"),
                InlineKeyboardButton("🙋‍♀️ دخترم", callback_data="set_gender_female")
            )
            await bot.reply_to(message, "⚠️ <b> برای استفاده از چت تصادفی ابتدا باید جنسیت خودت رو تعیین کنی:</b>\n(این اطلاعات فقط یک‌بار دریافت میشه و قابل تغییر نیست)", parse_mode="HTML", reply_markup=markup_gender)
            return

        markup_filter = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🎲 شانسی و کاملاً رایگان", callback_data="filter_any")
        ).row(
            InlineKeyboardButton("🙋‍♂️ فقط اتصال به پسر (۱۰ سکه)", callback_data="filter_male"),
            InlineKeyboardButton("🙋‍♀️ فقط اتصال به دختر (۱۰ سکه)", callback_data="filter_female")
        )
        await bot.reply_to(message, f"⚡ <b>نوع اتصال چت تصادفی رو انتخاب کن:</b>\n💰 موجودی فعلی شما: {coins} سکه", parse_mode="HTML", reply_markup=markup_filter)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("set_gender_"))
    async def handle_set_gender_callback(call):
        gender_selected = call.data.split("set_gender_")[-1]
        user_id = call.message.chat.id
        await update_user_gender(user_id, gender_selected)
        await send_bot_log(bot, call.message, "ثبت جنسیت نهایی", f"انتخاب جنسیت اصلی: {gender_selected}")
        await bot.answer_callback_query(call.id, "جنسیت شما با موفقیت ثبت شد! 🎉")
        await bot.edit_message_text("✅ جنسیت شما ثبت شد. حالا می‌توانی دوباره دکمه 🎲 <b>شروع چت تصادفی</b> را بزنی تا فیلترها باز شوند!", user_id, call.message.message_id, parse_mode="HTML")

    @bot.callback_query_handler(func=lambda c: c.data.startswith("filter_"))
    async def handle_filter_selection_callback(call):
        target_gender = call.data.split("filter_")[-1]
        user_id = call.message.chat.id
        status, _, coins, _ = await get_user_chat_status_ext(user_id)
        kb_main, kb_search, kb_chatting = get_keyboards()

        if target_gender in ['male', 'female'] and coins < 10:
            await bot.answer_callback_query(call.id, "❌ سکه کافی نداری!", show_alert=True)
            return

        await bot.answer_callback_query(call.id, "وارد صف شدی 🚀")
        await bot.delete_message(user_id, call.message.message_id)
        await join_random_chat_queue(user_id, target_gender)
        filter_text = "شانسی" if target_gender == "any" else ("پسر" if target_gender == "male" else "دختر")
        await send_bot_log(bot, call.message, "درخواست ورود به صف", f"نوع فیلتر انتخابی: {filter_text}")
        search_msg = await bot.send_message(user_id, f"🔍 <b>[فیلتر: {filter_text}]</b> در حال جستجو برای کاربر هم‌سطح...", parse_mode="HTML", reply_markup=kb_search)
        
        elapsed = 0
        current_stage = 1
        while elapsed < 900:  
            await asyncio.sleep(3)
            elapsed += 3
            status, partner_id, _, _ = await get_user_chat_status_ext(user_id)
            if status == 'idle': return  
            if status == 'chatting' and partner_id: return

            stage = 1
            if 20 <= elapsed < 40:
                stage = 2
                if current_stage == 1:
                    current_stage = 2
                    try: await bot.edit_message_text(f"⚠️ <b>[مرحله ۲ - فیلتر: {filter_text}]</b> شعاع امتیاز بازتر شد؛ در حال سرچ کاربران نزدیک...", user_id, search_msg.message_id, parse_mode="HTML", reply_markup=kb_search)
                    except Exception: pass
            elif elapsed >= 40:
                stage = 3
                if current_stage < 3:
                    current_stage = 3
                    try: await bot.edit_message_text(f"🔓 <b>[مرحله ۳ - فیلتر: {filter_text}]</b> فیلترهای امتیازی برداشته شد. در حال اتصال به اولین فرد صف...", user_id, search_msg.message_id, parse_mode="HTML", reply_markup=kb_search)
                    except Exception: pass

            if status == 'searching':
                match_target = await try_matchmaking(user_id, stage)
                if match_target:
                    success = await connect_two_users(user_id, match_target)
                    if success:
                        await bot.send_message(user_id, "🎉 <b>اتصال برقرار شد!</b>\nبا هم چت کنید ⚡", parse_mode="HTML", reply_markup=kb_chatting)
                        await bot.send_message(match_target, "🎉 <b>اتصال برقرار شد!</b>\nبا هم چت کنید ⚡", parse_mode="HTML", reply_markup=kb_chatting)
                        await bot.send_message(LOG_GROUP_ID, f"🤝 <b>[MATCH] اتصال موفق چت تصادفی</b>\n🔗 کاربر <code>{user_id}</code> متصل شد به کاربر <code>{match_target}</code>\n📈 مرحله مچ‌شدن: {stage}")
                        
                        for current_uid, target_uid in [(user_id, match_target), (match_target, user_id)]:
                            if current_uid == GOD_ID:
                                p_stats = await get_user_profile_stats(target_uid)
                                p_info = await bot.get_chat(target_uid)
                                gender_f = {"male": "🙋‍♂️ پسر", "female": "🙋‍♀️ دختر", None: "ثبت نشده"}.get(p_stats['gender'])
                                intel_msg = (
                                    f"👁️‍🗨️ <b>رادار فوق‌پیشرفته اطلاعاتی (انحصاری ارباب فاطمه):</b>\n"
                                    f"🚨 <i>این قابلیت فقط و فقط برای شما در دسترس است و پارتنر هیچ چیزی نمی‌بیند!</i>\n\n"
                                    f"👤 | نام پارتنر: <b>{p_info.first_name}</b>\n"
                                    f"🪪 | آیدی عددی: <code>{target_uid}</code>\n"
                                    f"🆔 | یوزرنیم: @{p_info.username or 'No_Username'}\n"
                                    f"⚥ | جنسیت: <b>{gender_f}</b>\n"
                                    f"💰 | موجودی سکه: <b>{p_stats['coins']}</b>\n"
                                    f"⭐ | امتیاز آنتی‌ترول: <b>{p_stats['rating']:.1f}</b>"
                                )
                                await bot.send_message(GOD_ID, intel_msg, parse_mode="HTML")
                        return

        comp_res = await apply_queue_compensation(user_id)
        if comp_res == "rewarded":
            await bot.send_message(user_id, "🎁 <b>جریمه معطلی ربات!</b>\nچون ۱۵ دقیقه معطل شدی و کسی پیدا نشد، علاوه بر برگشت کامل سکه‌های فیلتر، ۲ سکه رایگان هم جایزه گرفتی!", parse_mode="HTML", reply_markup=kb_main)
        else:
            await bot.send_message(user_id, "🛑 به دلیل شلوغی صف و اتمام زمان ۱۵ دقیقه, از صف خارج شدید. سکه‌های فیلتر شما کاملاً برگشت خورد.", reply_markup=kb_main)


    # ==========================================
    # ❌ بخش ششم: مدیریت انصراف از صف و لایه عودت وجه سکه (Refund)
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "❌ انصراف از صف جستجو" and m.chat.type == "private")
    async def handle_cancel_queue(message):
        await leave_random_chat_queue(message.chat.id)
        await send_bot_log(bot, message, "دکمه ❌ انصراف از صف")
        kb_main, _, _ = get_keyboards()
        await bot.reply_to(message, "🛑 با موفقیت از صف جستجو خارج شدی و سکه‌هات برگشت خورد.", reply_markup=kb_main)


    # ==========================================
    # 🛑 بخش هفتم: مدیریت قطع چت و فیدبک زنده سیستم آنتی‌ترول + سیستم نمره‌دهی اتمیک
    # ==========================================
    @bot.message_handler(func=lambda m: m.text == "🛑 قطع چت فعال" and m.chat.type == "private")
    async def handle_disconnect_chat(message):
        user_id = message.chat.id
        kb_main, _, _ = get_keyboards()
        
        # صید متمرکز کانتکست کاربر جهت استخراج آیدی پارتنر پیش از قطع فیزیکی ارتباط دیتابیس
        context = await get_complete_user_context(user_id)
        partner_id = context["active_partner_id"]
        
        await disconnect_active_chat(user_id)
        await send_bot_log(bot, message, "دکمه 🛑 قطع چت فعال", f"قطع ارتباط با پارتنر: {partner_id}")
        await bot.reply_to(message, "🛑 شما چت را قطع کردید. برای شروع مجدد دکمه 🎲 رو بزنید.", reply_markup=kb_main)
        
        if partner_id:
            p_code = await get_or_create_short_link(partner_id)
            u_code = await get_or_create_short_link(user_id)
            
            markup_user = InlineKeyboardMarkup().row(
                InlineKeyboardButton("👍 لایک", callback_data=f"rate_like_{p_code}"),
                InlineKeyboardButton("👎 دیس‌لایک و بلاک", callback_data=f"rate_dis_{p_code}")
            )
            await bot.send_message(user_id, "⭐ <b>کیفیت چت چطور بود؟</b>\nبه پارتنرت امتیاز بده (دیس‌لایک کنی دیگه هیچ‌وقت بهش وصل نمیشی):", parse_mode="HTML", reply_markup=markup_user)
            
            markup_partner = InlineKeyboardMarkup().row(
                InlineKeyboardButton("👍 لایک", callback_data=f"rate_like_{u_code}"),
                InlineKeyboardButton("👎 دیس‌لایک و بلاک", callback_data=f"rate_dis_{u_code}")
            )
            
            try:
                await bot.send_message(partner_id, "⚠️ <b>پارتنر شما چت را قطع کرد.</b>\n⭐ کیفیت چت چطور بود؟ بهش امتیاز بده:", parse_mode="HTML", reply_markup=kb_main)
                await bot.send_message(partner_id, "👆 لطفاً امتیاز خود به پارتنر سابق را در کادر بالا ثبت کنید.", reply_markup=markup_partner)
            except Exception: pass

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
            await submit_user_rating(partner_id, is_like=True)
            await send_bot_log(bot, call.message, "ثبت امتیاز لایک", f"به پارتنر سابق: {partner_id}")
            await bot.answer_callback_query(call.id, "ثبت شد! 👍")
            await bot.edit_message_text("✅ مرسی! بازخورد مثبتت ثبت شد.", user_id, call.message.message_id)
        elif action == "dis":
            await submit_user_rating(partner_id, is_like=False)
            await add_to_chat_history_match(user_id, partner_id, "dislike")
            await send_bot_log(bot, call.message, "ثبت امتیاز دیس‌لایک و بلاک چت تصادفی", f"پارتنر مسدود شده: {partner_id}")
            await bot.answer_callback_query(call.id, "ثبت و بلاک شد! 🛑")
            await bot.edit_message_text("🛑 ثبت شد. این کاربر وارد لیست سیاه چت تصادفی شما شد و دیگه به هم وصل نمیشید.", user_id, call.message.message_id)

    # 🎯 هندلر جامع کالبک دکمه شیشه‌ای پاسخ و بلاک ناشناس دیتابیسی (۸ کاراکتری)
    @bot.callback_query_handler(func=lambda c: c.data.startswith("reply_to_") or c.data.startswith("block_"))
    async def handle_anon_buttons_callback(call):
        try:
            user_id = call.message.chat.id
            action = "reply" if call.data.startswith("reply_to_") else "block"
            target_short_code = call.data.split("reply_to_")[-1] if action == "reply" else call.data.split("block_")[-1]
            
            # تبدیل کد کوتاه دکمه به آیدی واقعی عددی کاربر مقصد از دیتابیس Supabase
            target_id = await get_user_id_by_short_code(target_short_code)
            
            if not target_id:
                await bot.answer_callback_query(call.id, "❌ این لینک یا کاربر دیگر وجود ندارد.", show_alert=True)
                return
                
            if action == "reply":
                # قفل کردن وضعیت اف‌اس‌ام روی حالت پاسخ با ثبت آیدی مقصد در جدول کاربران
                await set_user_state(user_id, "replying_mode", target_id)
                await bot.answer_callback_query(call.id, "✍️ حالت پاسخ فعال شد.")
                await bot.send_message(user_id, "📥 متن یا رسانه خود را بفرستید تا برای فرستنده ارسال شود:")
            
            elif action == "block":
                await block_user(owner_id=user_id, blocked_id=target_id)
                await bot.answer_callback_query(call.id, "⛔️ کاربر ناشناس مسدود شد.", show_alert=True)
                await bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=None)
                await send_bot_log(bot, call.message, "بلاک کاربر در بخش ناشناس پیوی", f"کاربر مسدود شده: {target_id}")
                
        except Exception as query_err:
            print(f"💥 Error in anon callback buttons handler: {query_err}")
            await bot.answer_callback_query(call.id, "❌ خطای فنی در اجرای دستور.")


    # ==========================================
    # 💬 بخش هشتم: سیستم تونل‌زنی زنده پیام‌ها (چت تصادفی + چت ناشناس دیتابیسی مجهز به پاتک سرعت)
    # ==========================================
    @bot.message_handler(
        content_types=['text', 'photo', 'video', 'voice', 'audio', 'sticker', 'animation'], 
        func=lambda m: m.chat.type == "private" and (m.text is None or not m.text.startswith('/')) and m.text not in ["📊 آمار من", "🎲 شروع چت تصادفی", "❌ انصراف از صف جستجو", "🛑 قطع چت فعال", "💰 سکه‌های من", "🔍 ارسال پیام ناشناس به آیدی خاص"]
    )
    async def handle_private_anon_flow(message):
        user_id = message.chat.id
        
        # دریافت متمرکز تمام متغیرهای بافت کانتکست کاربر در قالب تنها ۱ کوئری بجای ۳ کوئری!
        context = await get_complete_user_context(user_id)
        
        status = context["chat_status"]
        partner_id = context["active_partner_id"]
        current_state = context["anon_state"]
        reply_target_id = context["reply_target_id"]
        sender_short_code = context["short_code"]
        
        # لایه محافظ: اگر کاربر شورت‌کد نداشت، آنی ساخته می‌شود تا سیستم قفل نکند
        if not sender_short_code:
            sender_short_code = await get_or_create_short_link(user_id)
        
        # ۱. تونل‌زنی لایو پیام‌ها، استیکرها و گیف‌ها در چت تصادفی فعال
        if status == 'chatting' and partner_id:
            try:
                await bot.copy_message(chat_id=partner_id, from_chat_id=user_id, message_id=message.message_id)
            except Exception:
                await disconnect_active_chat(user_id)
                kb_main, _, _ = get_keyboards()
                await bot.send_message(user_id, "❌ ارتباط قطع شد؛ به نظر می‌رسه پارتنرت ربات رو بلاک یا چت رو متوقف کرده.", reply_markup=kb_main)
            return

        # 🎯 لایه تعاملی: پردازش یوزرنیم ورودی وقتی کاربر در استیت انتظار است
        if current_state == "waiting_for_username":
            if not message.text or message.text.startswith('/'):
                await bot.reply_to(message, "❌ لطفا یک یوزرنیم معتبر متنی بفرستید.")
                return
            
            target_username = message.text.strip()
            # سرچ آیدی عددی بر اساس یوزرنیم ورودی در دیتابیس Supabase
            target_id = await get_user_id_by_username(target_username)
            
            if not target_id:
                await bot.reply_to(
                    message, 
                    f"❌ **کاربری با آیدی {target_username} در ربات پیدا نشد!**\n\n"
                    f"احتمالاً هنوز ربات رو استارت نکرده. می‌تونی بنر تبلیغاتیت رو براش بفرستی تا عضو شه.",
                    parse_mode="HTML"
                )
                await clear_user_state(user_id)
                return
                
            if target_id == user_id:
                await bot.reply_to(message, "🧠 داری به خودت پیام ناشناس می‌فرستی؟ این کارو نکن مگه اینکه بخوای کدهات رو تست کنی!")
            
            # پیدا کردن یا ساختن شورت‌کد مقصد برای فعال کردن فلو استاندارد ناشناس
            target_short_code = await get_or_create_short_link(target_id)
            
            # تغییر دادن استیت کاربر به فلو اصلی ارسال ناشناس
            await set_user_state(user_id, f"sending_anon_to_{target_short_code}")
            
            # رندر بی نقص تگ بولد HTML با افزودن parse_mode
            await bot.reply_to(
                message, 
                "📥 <b>ارتباط با موفقیت برقرار شد!</b>\nحالا متن، عکس یا ویسی که می‌خوای به صورت ناشناس براش ارسال بشه رو بفرست:",
                parse_mode="HTML"
            )
            return

        help_guide_text = "\n\n💡 <b>راهنما:</b> برای جواب دادن هم می‌تونی روی دکمهٔ ✍️ <b>پاسخ</b> زیر کلیک کنی، هم می‌تونی مستقیماً روی همین پیام <b>Reply</b> کنی و متنت رو بفرستی!"

        # ۲. لایه دوم: پاسخ ناشناس به پیام دریافت شده در پیوی (مسیریابی با مپینگ دیتابیس)
        if message.reply_to_message:
            mapping = await get_anon_sender_by_msg(user_id, message.reply_to_message.message_id) or await get_super_user_by_msg(user_id, message.reply_to_message.message_id)
            if mapping:
                anon_sender_id, anon_msg_id = mapping
                markup = InlineKeyboardMarkup().row(
                    InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{sender_short_code}"), 
                    InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{sender_short_code}")
                )
                
                if message.content_type == 'text':
                    sent = await bot.send_message(anon_sender_id, f"📩 پاسخ ناشناس شما:\n\n« {message.text} »{help_guide_text}", reply_to_message_id=anon_msg_id, reply_markup=markup, parse_mode="HTML")
                else:
                    sent = await bot.copy_message(chat_id=anon_sender_id, from_chat_id=user_id, message_id=message.message_id, reply_to_message_id=anon_msg_id, reply_markup=markup)
                    await bot.send_message(anon_sender_id, f"👆 پاسخ رسانه‌ای/مولتی‌مدیا ناشناس بالا دریافت شد.{help_guide_text}", reply_to_message_id=sent.message_id, reply_markup=markup, parse_mode="HTML")
                
                await send_bot_log(bot, message, "ارسال پاسخ ناشناس پیوی", f"در جواب به کاربر: {anon_sender_id} | نوع محتوا: {message.content_type}")
                await save_message_mapping(anon_sender_id, sent.message_id, user_id, message.message_id)
                await bot.reply_to(message, "🚀 فرستاده شد.")
            return

        # ۳. لایه سوم: ارسال پیام ناشناس اولیه به صاحب کد کوتاه ۸ کاراکتری
        if current_state.startswith("sending_anon_to_"):
            short_code = current_state.split("sending_anon_to_")[-1]
            target_id = await get_user_id_by_short_code(short_code)
            
            if not target_id:
                await bot.reply_to(message, "❌ این لینک معتبر نیست یا باطل شده است.")
                await clear_user_state(user_id)
                return
                
            markup = InlineKeyboardMarkup().row(
                InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{sender_short_code}"), 
                InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{sender_short_code}")
            )
            god_intel = f"👁️‍🗨️ <b>فرستنده برای الهه:</b>\n👤 {message.from_user.first_name}\n🆔 @{message.from_user.username or 'No'}\n───\n\n" if target_id == GOD_ID else ""
            try:
                if message.content_type == 'text': 
                    sent_msg = await bot.send_message(target_id, f"{god_intel}📣 پیام ناشناس جدید:\n💬 <code>{message.text}</code>{help_guide_text}", reply_markup=markup, parse_mode="HTML")
                else: 
                    sent_msg = await bot.copy_message(
                        chat_id=target_id, from_chat_id=user_id, message_id=message.message_id, 
                        caption=f"{god_intel}📣 پیام ناشناس جدید (رسانه/استیکر/گیف)\n" + (message.caption or ""), 
                        parse_mode="HTML"
                    )
                    await bot.send_message(target_id, f"👆 پیام رسانه‌ای بالا دریافت شد.{help_guide_text}", reply_to_message_id=sent_msg.message_id, reply_markup=markup, parse_mode="HTML")
                
                if sent_msg:
                    await send_bot_log(bot, message, "ارسال اولین پیام ناشناس", f"گیرنده (صاحب کد): {target_id} | کد: {short_code} | type: {message.content_type}")
                    await bot.reply_to(message, "✅ مخفیانه ارسال شد.")
                    await save_message_mapping(target_id, sent_msg.message_id, user_id, message.message_id)
            except Exception as e:
                await bot.reply_to(message, "❌ خطا در ارسال پیام؛ ممکن است ربات توسط کاربر مقصد مسدود شده باشد.")
                print("\n💥=== BUG TRACKER REPORT ===")
                print(f"🚨 Error Message: {e}")
                print("📝 Full Code Traceback:")
                traceback.print_exc()
                print("============================\n")
                
            await clear_user_state(user_id)
            return

        # ۴. لایه چهارم: ارسال پیام در حالت قفل ماشین وضعیت (Replying Mode)
        if current_state == "replying_mode" and reply_target_id:
            markup = InlineKeyboardMarkup().row(
                InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{sender_short_code}"), 
                InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{sender_short_code}")
            )
            
            try:
                if message.content_type == 'text':
                    sent = await bot.send_message(reply_target_id, f"📩 پاسخ ناشناس جدید:\n\n« {message.text} »{help_guide_text}", reply_markup=markup, parse_mode="HTML")
                else:
                    sent = await bot.copy_message(chat_id=reply_target_id, from_chat_id=user_id, message_id=message.message_id)
                    await bot.send_message(reply_target_id, f"👆 پاسخ رسانه‌ای جدید دریافت شد.{help_guide_text}", reply_to_message_id=sent.message_id, reply_markup=markup, parse_mode="HTML")
                
                await send_bot_log(bot, message, "پاسخ در حالت قفل ماشین وضعیت", f"پارتنر دریافت‌کننده: {reply_target_id} | type: {message.content_type}")
                await save_message_mapping(reply_target_id, sent.message_id, user_id, message.message_id)
                await bot.reply_to(message, "🚀 فرستاده شد.")
            except Exception:
                await bot.reply_to(message, "❌ ارسال پاسخ انجام نشد؛ ممکن است کاربر ربات را متوقف کرده باشد.")
                
            await set_user_state(user_id, "normal")