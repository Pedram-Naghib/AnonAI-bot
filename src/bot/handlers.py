from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReactionTypeEmoji, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from src.ai.client import generate_ai_response
from src.utils.crypto import encode_user_id, decode_user_id
from src.config import GROUP_CHAT_ID
import re
from src.database.db_manager import get_daily_group_logs
from src.ai.client import ai_client, types

# 📥 تزریق مستقیم توابع دیتابیس
from src.database.db_manager import (
    get_user_state, set_user_state, clear_user_state,
    save_message_mapping, get_anon_sender_by_msg,
    block_user, is_user_blocked, get_super_user_by_msg,
    log_message_to_db, get_user_profile_stats
)

# 🔴 مدیریت کاربران و سطوح دسترسی
GOD_ID = 6779908406          # آیدی الهه ربات (فاطمه)
SUPER_USERS = [247768888, 6779908406] # تو و فاطمه


def register_bot_handlers(bot: AsyncTeleBot):
    
    # ─── ۱. مدیریت دستور /start با کیبورد منوی آماده ───
    @bot.message_handler(commands=['start'])
    async def handle_start(message):
        bot_info = await bot.get_me()
        command_args = message.text.split()

        if message.chat.type != "private":
            return # ToDo
        user_id = message.chat.id
        
        # 🎛 ساخت کیبورد منوی اصلی ربات (سنجاق شده به پایین صفحه)
        main_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        btn_stats = KeyboardButton("📊 آمار من")
        # اینجا می‌توانی دکمه‌های دیگر را هم در آینده اضافه کنی، فعلاً این دکمه را می‌گذاریم:
        main_keyboard.add(btn_stats)
        
        # بررسی ورود از طریق لینک ناشناس
        if len(command_args) > 1:
            target_owner_id_encoded = command_args[1]
            target_owner_id = decode_user_id(target_owner_id_encoded)
            
            if target_owner_id and user_id != target_owner_id:
                if await is_user_blocked(owner_id=target_owner_id, blocked_id=user_id):
                    await bot.reply_to(message, "❌ شما توسط این کاربر بلاک شده‌اید و امکان ارسال پیام ناشناس را ندارید.", reply_markup=main_keyboard)
                    return
                
                await set_user_state(user_id, f"sending_anon_to_{target_owner_id_encoded}")
                await bot.reply_to(message, "📥 شما در حال ارسال پیام ناشناس هستید.\nمی‌توانید متن، عکس، فیلم، ویس یا صدای خود را ارسال کنید:", reply_markup=main_keyboard)
                return
            elif not target_owner_id:
                await bot.reply_to(message, "❌ این لینک معتبر نیست یا دستکاری شده است.", reply_markup=main_keyboard)
                return

        # ساخت لینک انکود شده و امن
        secret_code = encode_user_id(user_id)
        anon_link = f"https://t.me/{bot_info.username}?start={secret_code}"
        
        if user_id == GOD_ID:
            msg = (
                f"سلام و درود ارباب فاطمه. 🙇‍♂️\n"
                f"هوش مصنوعی گوش به فرمان شماست.\n\n"
                f"👁️‍🗨️ **دسترسی ارشد ویژه:**\n"
                f"شما برخلاف کاربران عادی، توانایی مشاهدهٔ اطلاعات دقیق فرستندهٔ پیام‌ها را دارید.\n\n"
                f"🔗 **لینک ناشناس ارباب:**\n"
                f"`{anon_link}`")
        else:
            msg = (
                "👋 به ربات پیام ناشناس خوش آمدید!\n\n"
                f"🔗 این لینک اختصاصی شماست:\n`{anon_link}`\n\n"
                "این لینک را در بیو یا استوری خود بگذارید. هر کس روی آن کلیک کند، "
                "می‌تواند برای شما پیام ناشناس بفرستد و شما همین‌جا پاسخشان را بدهید!"
            )
            
        # ارسال پیام خوش‌آمدگویی همراه با منوی دکمه‌ها
        await bot.reply_to(message, msg, parse_mode="Markdown", reply_markup=main_keyboard)

    # ─── ۲.الف: مدیریت آلبوم‌ها و فایل‌های دسته‌جمعی (Media Groups) ───
    @bot.message_handler(func=lambda message: message.media_group_id is not None, content_types=['photo', 'video', 'audio'])
    async def handle_media_group(message):
        user_id = message.chat.id
        
        if message.chat.type in ['group', 'supergroup'] and message.caption and not message.caption.startswith('/'):
            await log_message_to_db(
                user_id=message.from_user.id,
                username=message.from_user.username or "NoUsername",
                first_name=message.from_user.first_name,
                text=message.caption
            )

        current_state, _ = await get_user_state(user_id)

        if current_state.startswith("sending_anon_to_"):
            target_id = decode_user_id(current_state.split("_")[-1])
            encoded_id = encode_user_id(user_id)
            
            media_group = await bot.get_media_group(message.chat.id, message.media_group_id)
            
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{encoded_id}"),
                InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{encoded_id}")
            )

            god_intelligence = ""
            if target_id == GOD_ID:
                f_user = message.from_user
                username_text = f"@{f_user.username}" if f_user.username else "ندارد ❌"
                last_name_text = f_user.last_name if f_user.last_name else "ندارد"
                god_intelligence = (
                    "👁️‍🗨️ <b>مشخصات فرستندهٔ آلبوم برای الهه ربات:</b>\n"
                    f"👤 نام: {f_user.first_name}\n"
                    f"👥 نام خانوادگی: {last_name_text}\n"
                    f"🆔 یوزرنیم: {username_text}\n"
                    "───────────────────────\n\n"
                )

            original_caption = media_group[0].caption if media_group[0].caption else ""
            media_group[0].caption = (
                f"{god_intelligence}"
                f"📣 یک آلبوم ناشناس مالتی‌مدیا دریافت کردی:\n\n"
                f"💬 <code>{original_caption}</code>\n\n"
                f"📌 <b>راهنمای پاسخ:</b>\n"
                f"می‌توانی از دکمه‌های شیشه‌ای زیر برای تعامل مستقیم استفاده کنی."
            )
            media_group[0].parse_mode = "HTML"

            try:
                sent_messages = await bot.send_media_group(target_id, media_group)
                if sent_messages:
                    await bot.edit_message_reply_markup(chat_id=target_id, message_id=sent_messages[0].message_id, reply_markup=markup)
                    await bot.reply_to(message, "✅ آلبوم مالتی‌مدیای شما با موفقیت و کاملاً مخفیانه ارسال شد.")
                    
                    # ذخیره دوطرفه نگاشت پیام آلبوم در دیتابیس
                    await save_message_mapping(
                        user_chat_id=target_id,
                        user_msg_id=sent_messages[0].message_id,
                        anon_sender_id=user_id,
                        anon_msg_id=message.message_id
                    )
            except Exception as e:
                print(f"Error in media group routing: {e}")
                await bot.reply_to(message, "❌ ارسال آلبوم ناموفق بود.")
            
            await clear_user_state(user_id)
            return

    # ─── ۶. گرفتن آیدی عددی چت فعلی ───
    @bot.message_handler(commands=['id'])
    async def handle_get_chat_id(message):
        chat_id = message.chat.id
        response_text = f"🆔 آیدی این چت/گروه: `{chat_id}`\n"
        try:
            await bot.reply_to(message, response_text, parse_mode="Markdown")
        except Exception as e:
            print(f"❌ Error sending ID: {e}")


    # ─── ۶. گرفتن آیدی عددی چت فعلی ───
    @bot.message_handler(commands=['gp'])
    async def handle_send_msg_to_gp(message):
        chat_id = message.chat.id
        if chat_id not in SUPER_USERS:
            return
        try:
            text = message.text.split("/gp ")
            await bot.send_message(GROUP_CHAT_ID, text[-1], reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            print(f"❌ Error sending ID: {e}")

    # 🔗 شلیک خودکار با دیدن لینک گروه (بدون نیاز به دستور)
    @bot.message_handler(regexp=r"^https:\/\/t\.me\/c\/1434396268\/(\d+)\s+(.*)")
    async def handle_auto_reply_by_link(message):
        chat_id = message.chat.id
        
        # سد دفاعی دسترسی سوپریوزرها
        if chat_id not in SUPER_USERS:
            return
            
        try:
            # استخراج آیدی پیام و متن از طریق رگکس
            match = re.match(r"^https:\/\/t\.me\/c\/1434396268\/(\d+)\s+(.*)", message.text)
            
            if match:
                reply_to_msg_id = int(match.group(1)) # عدد آخر لینک (مثلاً 548058)
                clean_text = match.group(2)          # کل متن بعد از لینک
                
                # ارسال ریپلای به گروه
                await bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=clean_text,
                    reply_to_message_id=reply_to_msg_id,
                    reply_markup=ReplyKeyboardRemove()
                )
                await bot.reply_to(message, f"🎯 بدون دستور و با موفقیت روی پیام `{reply_to_msg_id}` ریپلای شد!")
                
        except Exception as e:
            print(f"❌ Error in auto-reply trigger: {e}")
            await bot.reply_to(message, f"❌ خطای ریپلای خودکار: {e}")


    @bot.message_handler(commands=['test_summary'])
    async def handle_test_summary(message):
        chat_id = message.chat.id
        
        # ۱. سد دفاعی دسترسی: فقط تو و فاطمه
        if chat_id not in SUPER_USERS:
            return
            
        await bot.reply_to(message, "📥 در حال استخراج چت‌های ۲۴ ساعت گذشته از سوپابیس و ارسال به جمینای... لطفاً چند ثانیه صبر کن ستون.")
        await bot.send_chat_action(chat_id, action="typing")
        
        try:
            # ۲. کشیدن دیتای واقعی از دیتابیس
            rows = await get_daily_group_logs()
            
            # ۳. مصلحت‌سنجی: اگر دیتابیس خالی بود، دیتای فیک تزریق کن تا تست متوقف نشود
            if not rows:
                await bot.send_message(chat_id, "💡 دیتابیس خالی بود ستون! برای اینکه تست نخوابه، دارم دیتای نمونه (Mock) به جمینای می‌دم...")
                rows = [
                    ("Pedram", "pedram_naghib", "حاجی این ربات چت ناشناس عجب چیزی شده بالاخره ران شد"),
                    ("Ali", "ali_test", "کص‌دست کدو اشتباه زدی باز که ارور ۴۰۰ داد"),
                    ("Pedram", "pedram_naghib", "خفه بابا درستش کردم مشکل از پلتفرم گوگل بود"),
                    ("Reza", "reza_98", "چاکر همگی، دمت گرم پدرام ردیفه"),
                    ("Mamad", "mamad_vulgar", "دهنتون سرویس کصکشا چقدر چت می‌کنید اسکل‌ها بگیرید بخوابید")
                ]

            # ۴. پردازش و دسته‌بندی پیام‌ها در پایتون
            user_chats = {}
            message_counts = {}
            
            for first_name, username, text in rows:
                user_key = f"{first_name} (@{username})" if username else first_name
                if user_key not in user_chats:
                    user_chats[user_key] = []
                user_chats[user_key].append(text)
                message_counts[user_key] = message_counts.get(user_key, 0) + 1

            # رتبه‌بندی دقیق بر اساس پایتون
            top_speakers = sorted(message_counts.items(), key=lambda x: x[1], reverse=True)
            ranking_context = "👑 EXACT RANKING BY MESSAGE COUNT:\n"
            for index, (user, count) in enumerate(top_speakers, 1):
                ranking_context += f"{index}. {user}: {count} messages\n"

            formatted_logs = ""
            for user, messages in user_chats.items():
                formatted_logs += f"=== USER: {user} ===\n"
                for msg in messages:
                    formatted_logs += f"- {msg}\n"
                formatted_logs += "\n"

            # ۵. پرامپت اصلی، سمی و خلاصه شده هومبان
            analytics_instruction = """
            You are Humban, a brutally honest, highly sarcastic, and witty group analyst for a close Persian crew.
            Your job is to generate the "Daily Group Report" exactly with the following format. 
            
            🚨 CRITICAL CONSTRAINT: Telegram has a strict character limit. Your entire response MUST be concise, punchy, and short. Keep the total output strictly UNDER 2500 characters. Do NOT write long essays for each section. Keep roasts short but lethal.
            
            Do NOT use markdown # headers. Use bold informal Persian like **تیتر**.
            
            1. **📊 گه خور ترین ها**: List exactly top users based on the EXACT RANKING. Add a very short, savage comment.
            2. **⌨️ کص‌دست‌ترین‌ها**: List users with typos/fast-typing mistakes and roast them in one line.
            3. **🤬 بیشعورترین‌ها**: List users who used the most profanity or rude tone.
            4. **🔥 سوژه روز**: Summarize the main funny drama/hot topic today in maximum 3-4 juicy, cinematic sentences.
            5. **💬 جمله برتر روز**: Quote one exact funny line and roast them hard.

            Tone: Heavy Persian street slang (حاجی، سم، اسید، سوتون، بوی مصلحت). Be an absolute roaster, but keep it highly condensed and brief.
            """

            full_context = f"{ranking_context}\n\nHere is the chat data:\n\n{formatted_logs}"

            # ۶. شلیک به API گوگل جمینای با مکانیزم سوئیچ خودکار زاپاس
            safety_configs = [
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH)
            ]

            try:
                # 🚀 تلاش اول با مدل اصلی و سریع‌تر
                print("🧠 Querying primary model (gemini-2.5-flash)...")
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=full_context,
                    config=types.GenerateContentConfig(
                        system_instruction=analytics_instruction,
                        safety_settings=safety_configs
                    )
                )
            except Exception as google_error:
                # 🔄 پاتک فنی: اگر مدل اصلی شلوغ بود یا ۵۰۳ داد، فوراً برو روی مدل پایدار ۱.۵
                print(f"⚠️ Primary model overloaded ({google_error}). Switching to backup (gemini-1.5-flash)...")
                response = ai_client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=full_context,
                    config=types.GenerateContentConfig(
                        system_instruction=analytics_instruction,
                        safety_settings=safety_configs
                    )
                )
            
            report_text = response.text if response.text else "امروز آمار خالیه ستون."
            
            # ۷. ارسال خروجی مستقیم به پیویِ خودت
            await bot.send_message(chat_id=chat_id, text=f"🧪 **[گزارش تست زنده هومبان - خروجی اختصاصی پیوی]**\n\n{report_text}", parse_mode="Markdown")
            
        except Exception as e:
            print(f"❌ Error in /test_summary command: {e}")
            await bot.send_message(chat_id=chat_id, text=f"❌ تست با خطا مواجه شد: {e}")


    # هندلر فعال‌سازی با پیام متنی "📊 آمار من" در پیوی ربات
    @bot.message_handler(func=lambda message: message.text == "📊 آمار من" and message.chat.type == "private")
    async def handle_my_stats(message):
        user_id = message.chat.id
        first_name = message.from_user.first_name
        
        # استخراج آمار زنده از دیتابیس
        stats = await get_user_profile_stats(user_id)
        
        # چیدمان دقیق قالب درخواستی پدرام
        response_text = (
            f"📊 **آمار من**\n\n"
            f"👤 | نام : {first_name}\n"
            f"🪪 | ایدی : `{user_id}`\n"
            f"✍ | تعداد پیام‌های ارسالی گروه : {stats['sent']}\n"
            f"📬 | تعداد پیام‌های ناشناس دریافتی : {stats['received']}\n"
            f"⛔️ | تعداد افراد بلاک شده : {stats['blocked']}"
        )
        
        await bot.reply_to(message, response_text, parse_mode="Markdown")

    # ─── ۲.ب: مدیریت پیام‌های انفرادی و تکی ───
    @bot.message_handler(func=lambda message: message.media_group_id is None, content_types=['text', 'photo', 'video', 'voice', 'audio'])
    async def handle_all_messages(message):
        user_id = message.chat.id
        user_text = message.text
        encoded_id = encode_user_id(user_id)
        
        # 🚨 سد دفاعی: فقط اگر پیام در گروه اصلی (OG) بود، لاگ دیتابیس فعال شود
        if message.chat.id == GROUP_CHAT_ID and message.caption and not message.caption.startswith('/'):
            await log_message_to_db(
                user_id=message.from_user.id,
                username=message.from_user.username or "NoUsername",
                first_name=message.from_user.first_name,
                text=message.caption
            )

        # 🚀 سناریو پاسخ از طریق ریپلای مستقیم (Native Reply)
        if message.chat.type == 'private' and message.reply_to_message:
            replied_msg_id = message.reply_to_message.message_id
            
            # ابتدا بررسی مپینگ برای فهمیدن اینکه پیام ریپلای شده مال غریبه است یا سوپریوزر
            mapping = await get_anon_sender_by_msg(user_chat_id=user_id, user_msg_id=replied_msg_id)
            
            # اگر مال غریبه عادی نبود، شاید سوپریوزر (مثل فاطمه) دارد به پیام فرستاده شده جواب مستقیم می‌دهد
            if not mapping:
                mapping = await get_super_user_by_msg(anon_sender_id=user_id, anon_msg_id=replied_msg_id)
            
            if mapping:
                anon_sender_id, anon_msg_id = mapping  
                
                reply_markup = InlineKeyboardMarkup()
                reply_markup.row(
                    InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{encoded_id}"),
                    InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{encoded_id}")
                )
                
                try:
                    if message.content_type == 'text':
                        sent_reply = await bot.send_message(
                            anon_sender_id, 
                            f"📩 یک پاسخ از ناشناس شما دریافت شد:\n\n« {user_text} »",
                            reply_to_message_id=anon_msg_id,
                            reply_markup=reply_markup,
                            parse_mode="HTML"
                        )
                        await bot.reply_to(message, "🚀 پاسخت برای اون شخص فرستاده شد.")
                        
                        # مپ کردن برعکس دیتا جهت تداوم پینگ‌پنگی چت و حفظ ری‌آکشن‌ها
                        await save_message_mapping(
                            user_chat_id=anon_sender_id,
                            user_msg_id=sent_reply.message_id,
                            anon_sender_id=user_id,
                            anon_msg_id=message.message_id
                        )
                    else:
                        await bot.reply_to(message, "⚠️ در حالت ریپلای مستقیم، فقط می‌توانید پیام متنی ارسال کنید.")
                except Exception as e:
                    print(f"Error in native reply routing: {e}")
                    await bot.reply_to(message, "❌ ارسال پاسخ ناموفق بود. کاربر ربات را بلاک کرده.")
                return

        # 🕵️‍♂️ جریان اصلی چت ناشناس
        current_state, reply_target_id = await get_user_state(user_id)
        
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{encoded_id}"),
            InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{encoded_id}")
        )

        # ارسال پیام به طرف مقابل
        if current_state.startswith("sending_anon_to_"):
            target_id = decode_user_id(current_state.split("_")[-1])
            anon_caption = f"« {message.caption} »\n\n" if message.caption else ""
            
            god_intelligence = ""
            if target_id == GOD_ID:
                f_user = message.from_user
                username_text = f"@{f_user.username}" if f_user.username else "ندارد ❌"
                last_name_text = f_user.last_name if f_user.last_name else "ندارد"
                god_intelligence = (
                    "👁️‍🗨️ <b>مشخصات فرستنده برای الهه ربات:</b>\n"
                    f"👤 نام: {f_user.first_name}\n"
                    f"👥 نام خانوادگی: {last_name_text}\n"
                    f"🆔 یوزرنیم: {username_text}\n"
                    "───────────────────────\n\n"
                )

            caption_text = (
                f"{god_intelligence}"
                f"📣 یک پیام ناشناس تصویری/صوتی دریافت کردی:\n\n"
                f"{anon_caption}"
                f"📌 <b>راهنمای پاسخ:</b>\n"
                f"هم می‌توانی روی همین پیام ریپلای کنی، و هم از دکمهٔ زیر استفاده کنی."
            )
            
            try:
                sent_msg = None
                if message.content_type == 'text':
                    text_msg_content = (
                        f"{god_intelligence}"
                        f"📣 یک پیام ناشناس جدید دریافت کردی:\n\n"
                        f"💬 <code>{user_text}</code>\n\n"
                        f"📌 <b>راهنمای پاسخ:</b>\n"
                        f"هم می‌توانی روی همین پیام ریپلای کنی، و هم از دکمهٔ «✍️ پاسخ» زیر استفاده کنی."
                    )
                    sent_msg = await bot.send_message(target_id, text_msg_content, reply_markup=markup, parse_mode="HTML")
                elif message.content_type == 'photo':
                    file_id = message.photo[-1].file_id
                    sent_msg = await bot.send_photo(target_id, file_id, caption=caption_text, reply_markup=markup, parse_mode="HTML")
                elif message.content_type == 'video':
                    sent_msg = await bot.send_video(target_id, message.video.file_id, caption=caption_text, reply_markup=markup, parse_mode="HTML")
                elif message.content_type == 'voice':
                    sent_msg = await bot.send_voice(target_id, message.voice.file_id, caption=caption_text, reply_markup=markup, parse_mode="HTML")
                elif message.content_type == 'audio':
                    sent_msg = await bot.send_audio(target_id, message.audio.file_id, caption=caption_text, reply_markup=markup, parse_mode="HTML")

                if sent_msg:
                    await bot.reply_to(message, "✅ پیام ناشناس شما با موفقیت ارسال شد.")
                    await save_message_mapping(
                        user_chat_id=target_id,
                        user_msg_id=sent_msg.message_id,
                        anon_sender_id=user_id,
                        anon_msg_id=message.message_id
                    )
            except Exception as e:
                print(f"Error in single message routing: {e}")
                await bot.reply_to(message, "❌ ارسال پیام ناموفق بود.")
            
            await clear_user_state(user_id)
            return

        # پاسخ به پیام از طریق دکمه شیشه‌ای
        if current_state == "replying_mode" and reply_target_id:
            mapping = await get_anon_sender_by_msg(user_chat_id=user_id, user_msg_id=reply_target_id)
            
            if not mapping:
                mapping = await get_super_user_by_msg(anon_sender_id=user_id, anon_msg_id=reply_target_id)
                
            if mapping:
                anon_sender_id, anon_msg_id = mapping
                
                reply_markup = InlineKeyboardMarkup()
                reply_markup.row(
                    InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_to_{encoded_id}"),
                    InlineKeyboardButton("⛔️ بلاک", callback_data=f"block_{encoded_id}")
                )
                
                try:
                    if message.content_type == 'text':
                        sent_reply = await bot.send_message(
                            anon_sender_id, 
                            f"📩 یک پاسخ از ناشناس شما دریافت شد:\n\n« {user_text} »",
                            reply_to_message_id=anon_msg_id,
                            reply_markup=reply_markup,
                            parse_mode="HTML"
                        )
                        await bot.reply_to(message, "🚀 پاسخت برای اون شخص فرستاده شد.")
                        
                        await save_message_mapping(
                            user_chat_id=anon_sender_id,
                            user_msg_id=sent_reply.message_id,
                            anon_sender_id=user_id,
                            anon_msg_id=message.message_id
                        )
                    else:
                        await bot.reply_to(message, "⚠️ از طریق وضعیت دکمه فقط می‌توانید پاسخ متنی بفرستید.")
                except Exception as e:
                    print(f"Error in inline button reply routing: {e}")
                    await bot.reply_to(message, "❌ ارسال پاسخ ناموفق بود. کاربر ربات را بلاک کرده.")
            else:
                await bot.reply_to(message, "❌ خطا: پیام متناظر این دکمه در دیتابیس یافت نشد.")
            
            await set_user_state(user_id, "normal")
            return

        # چت عادی با هوش مصنوعی (برای تو و فاطمه)
        if user_id in SUPER_USERS:
            if message.content_type == 'text':
                await bot.send_chat_action(user_id, action="typing")
                is_fateme = (user_id == GOD_ID)
                ai_reply = await generate_ai_response(user_text, is_god=is_fateme)
                await bot.reply_to(message, ai_reply)
            else:
                await bot.reply_to(message, "🤖 من در حال حاضر فقط متون شما را برای پردازش هوش مصنوعی درک می‌کنم.")
        else:
            return

    # ─── ۳. هندل کردن کلیک روی دکمه "پاسخ" ───
    @bot.callback_query_handler(func=lambda call: call.data.startswith("reply_to_"))
    async def handle_reply_callback(call):
        user_id = call.message.chat.id
        incoming_msg_id = call.message.message_id
        anon_encoded_id = call.data.split("reply_to_")[-1]
        anonymous_user_id = decode_user_id(anon_encoded_id)
        
        if anonymous_user_id:
            await set_user_state(user_id, "replying_mode", reply_target_id=incoming_msg_id)
            await bot.send_message(
                user_id, 
                "✍️ بسیار خب، پاسخی که می‌خواهی به این شخص بدهی را بنویس و ارسال کن."
            )
        else:
            await bot.send_message(user_id, "❌ این فرستنده دیگر معتبر نیست.")
            
        await bot.answer_callback_query(call.id)

    # ─── ۴. هندل کردن کلیک روی دکمه "بلاک" ───
    @bot.callback_query_handler(func=lambda call: call.data.startswith("block_"))
    async def handle_block_callback(call):
        user_id = call.message.chat.id
        message_id = call.message.message_id
        anon_encoded_id = call.data.split("block_")[-1]
        anonymous_user_id = decode_user_id(anon_encoded_id)
        
        if anonymous_user_id:
            await block_user(owner_id=user_id, blocked_id=anonymous_user_id)
            await bot.answer_callback_query(call.id, "کاربر با موفقیت بلاک شد! 🛑")
            
            current_text = call.message.text if call.message.text else call.message.caption
            updated_text = f"{current_text}\n\n❌ **این فرستنده توسط شما بلاک شد.**"
            
            if call.message.text:
                await bot.edit_message_text(chat_id=user_id, message_id=message_id, text=updated_text, parse_mode="Markdown")
            else:
                await bot.edit_message_caption(chat_id=user_id, message_id=message_id, caption=updated_text, parse_mode="Markdown")
        else:
            await bot.answer_callback_query(call.id, "❌ خطایی در رمزگشایی رخ داد.", show_alert=True)

    # ─── ۵. سینک دایمی و دوطرفه ری‌اکشن‌ها (اصلاح نهایی برای فاطمه و غریبه‌ها) ───
    @bot.message_reaction_handler()
    async def handle_reactions(message_reaction):
        chat_id = message_reaction.chat.id
        message_id = message_reaction.message_id
        new_reactions = message_reaction.new_reaction
        
        if not new_reactions:
            return
            
        target_emoji = new_reactions[0].emoji
        
        # حالت اول: ری‌آکشن در پیویِ صاحبان ربات رخ داده (ما می‌خواهیم بفرستیم برای غریبه)
        if chat_id in SUPER_USERS:
            mapping = await get_anon_sender_by_msg(chat_id, message_id)
            if mapping:
                anon_sender_id, anon_msg_id = mapping
                try:
                    await bot.set_message_reaction(
                        chat_id=anon_sender_id,
                        message_id=anon_msg_id,
                        reaction=[ReactionTypeEmoji(target_emoji)]
                    )
                except Exception as e:
                    print(f"Failed to sync reaction to anon: {e}")
                    
        # حالت دوم: ری‌آکشن در پیویِ غریبه رخ داده (ما می‌خواهیم منتقل کنیم به سوپریوزر/فاطمه)
        else:
            # جستجو بر اساس آیدی پیام چتِ غریبه به عنوان فرستنده اصلی برای سوپریوزرها
            mapping = await get_super_user_by_msg(anon_sender_id=chat_id, anon_msg_id=message_id)
            
            # اگر با متد سوپریوزر پیدا نشد، چک کردن متد عادی نقشه پیام
            if not mapping:
                mapping = await get_anon_sender_by_msg(user_chat_id=chat_id, user_msg_id=message_id)
                
            if mapping:
                super_user_id, super_msg_id = mapping
                try:
                    await bot.set_message_reaction(
                        chat_id=super_user_id,
                        message_id=super_msg_id,
                        reaction=[ReactionTypeEmoji(target_emoji)]
                    )
                except Exception as e:
                    print(f"Failed to sync reaction to superuser: {e}")