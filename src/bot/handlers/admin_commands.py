import re
import traceback
import asyncio
from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReplyKeyboardRemove, InputSticker

# وارد کردن تنظیمات و توابع پایه مورد نیاز
from src.config import GROUP_CHAT_ID, EMOJI
from src.database.db_manager import get_connection_pool

GOD_ID = 6779908406          
SUPER_USERS = [8627765327, 6779908406]

def register_admin_handlers(bot: AsyncTeleBot):

    # ==========================================
    # ⚙️ دستور دریافت آیدی چت یا گروه
    # ==========================================
    @bot.message_handler(commands=['id'])
    async def handle_get_chat_id(message):
        try:
            # 🔧 اصلاح پارامتر parse_mode به HTML جهت رندر صحیح تگ اموجی
            await bot.reply_to(message, f"{EMOJI['id']['html']} آیدی این چت/گروه: <code>{message.chat.id}</code>\n", parse_mode="HTML")
        except Exception as e:
            print(f"❌ Error sending ID: {e}")

    # ==========================================
    # ⚙️ دستور ارسال پیام مستقیم به گروه از طریق ربات
    # ==========================================
    @bot.message_handler(commands=['gp'])
    async def handle_send_msg_to_gp(message):
        if message.chat.id not in SUPER_USERS: return
        try:
            text = message.text.split("/gp ")
            if len(text) > 1:
                await bot.send_message(GROUP_CHAT_ID, text[-1], reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            print(f"❌ Error sending gp message: {e}")

    # ==========================================
    # ⚙️ دستور ریپلای خودکار روی لینک‌های پرایوت گروه
    # ==========================================
    @bot.message_handler(regexp=r"^https:\/\/t\.me\/c\/1434396268\/(\d+)\s+(.*)")
    async def handle_auto_reply_by_link(message):
        if message.chat.id not in SUPER_USERS: return
        try:
            match = re.match(r"^https:\/\/t\.me\/c\/1434396268\/(\d+)\s+(.*)", message.text)
            if match:
                reply_to_msg_id = int(match.group(1))
                clean_text = match.group(2)
                await bot.send_message(GROUP_CHAT_ID, text=clean_text, reply_to_message_id=reply_to_msg_id, reply_markup=ReplyKeyboardRemove())
                await bot.reply_to(message, f"{EMOJI['target']['html']} روی پیام <code>{reply_to_msg_id}</code> ریپلای شد!", parse_mode="HTML")
        except Exception as e:
            print(f"❌ Error in link auto-reply: {e}")

    # ==========================================
    # 👑 دستور ویژه مدیریت: دریافت آمار پیشرفته دیتابیس کاربران فعال
    # ==========================================
    @bot.message_handler(commands=['db_stats'], func=lambda m: m.chat.type == "private" and m.from_user.id in SUPER_USERS)
    async def handle_god_db_stats(message):
        await bot.send_chat_action(message.chat.id, 'typing')
        pool = await get_connection_pool()
        
        try:
            async with pool.acquire() as conn:
                total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
                total_dead_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE anon_state = 'blocked_bot'")
                
                query = """
                    SELECT 
                        u.user_id, 
                        u.first_name, 
                        u.username,
                        COALESCE(r.received_count, 0) AS received,
                        COALESCE(s.sent_count, 0) AS sent
                    FROM users u
                    LEFT JOIN (
                        SELECT user_chat_id, COUNT(*) AS received_count 
                        FROM message_map 
                        GROUP BY user_chat_id
                    ) r ON u.user_id = r.user_chat_id
                    LEFT JOIN (
                        SELECT anon_sender_id, COUNT(*) AS sent_count 
                        FROM message_map 
                        GROUP BY anon_sender_id
                    ) s ON u.user_id = s.anon_sender_id
                    WHERE u.anon_state != 'blocked_bot'
                    ORDER BY (COALESCE(r.received_count, 0) + COALESCE(s.sent_count, 0)) DESC
                    LIMIT 30;
                """
                
                rows = await conn.fetch(query)
                if not rows:
                    await bot.reply_to(message, f"{EMOJI['whisper_read']['html']} هیچ کاربری یافت نشد.\n👥 کل اعضا: {total_users}", parse_mode="HTML")
                    return

                async def check_and_clean_user(row):
                    uid = row['user_id']
                    try:
                        await asyncio.wait_for(bot.send_chat_action(uid, 'typing'), timeout=1.5)
                        return row, True
                    except Exception:
                        async with pool.acquire() as db_conn:
                            await db_conn.execute("UPDATE users SET anon_state = 'blocked_bot', chat_status = 'idle', active_partner_id = NULL WHERE user_id = $1", uid)
                        return row, False

                tasks = [check_and_clean_user(row) for row in rows]
                checked_results = await asyncio.gather(*tasks)

                live_users_count = total_users - total_dead_users

                report_lines = [
                    f"{EMOJI['gem']['html']} <b>گزارش ارشد وضعیت دیتابیس</b>\n",
                    f"{EMOJI['profile']['html']} کل کاربران ثبت شده: <b>{total_users}</b>",
                    f"{EMOJI['green_dot']['html']} کاربران فعال و زنده: <b>{live_users_count}</b>",
                    f"{EMOJI['red_dot']['html']} مسدودکنندگان شناسایی‌شده: <b>{total_dead_users}</b>\n",
                    f"{EMOJI['magnifiyer']['html']} <i>۲۰ کاربر برتر بر اساس بیشترین حجم تعاملات ناشناس:</i>\n"
                ]
                
                valid_count = 0
                for row, is_active in checked_results:
                    if not is_active: continue 
                    
                    valid_count += 1
                    uid = row['user_id']
                    name = row['first_name'] or "Unknown"
                    username = f"@{row['username']}" if row['username'] else "بدون یوزرنیم"
                    received = row['received']
                    sent = row['sent']
                    
                    line = (
                        f"{valid_count}. {EMOJI['profile']['html']} <b>{name}</b> (<code>{uid}</code>) | {username}\n"
                        f"   {EMOJI['recieve']['html']} دریافتی: <b>{received}</b> | {EMOJI['send']['html']} ارسالی: <b>{sent}</b>\n"
                        f"   ➖"
                    )
                    report_lines.append(line)
                    
                    if valid_count >= 20: break

                final_report = "\n".join(report_lines)
                await bot.reply_to(message, final_report, parse_mode="HTML")
                
        except Exception as err:
            print(f"💥 Admin Stats Command Failed: {err}")
            traceback.print_exc()
            await bot.reply_to(message, f"{EMOJI['ban']['html']} خطای فنی در استخراج اطلاعات از دیتابیس.", parse_mode="HTML")

    # ==========================================
    # 👑 دستور ویژه مدیریت: ارسال پیام همگانی دسته‌ای به کل ربات
    # ==========================================
    @bot.message_handler(commands=['bc'], func=lambda m: m.chat.type == "private" and m.from_user.id in SUPER_USERS)
    async def handle_bulk_broadcast(message):
        try:
            command_text = message.text.split("/bc ", 1)
            
            if len(command_text) < 2:
                await bot.reply_to(
                    message, 
                    f"{EMOJI['caution']['html']} <b>فرمت اشتباه است!</b>\n"
                    "لطفاً متن پیام خود را با یک فاصله بعد از دستور بنویسید.\n"
                    "مثال:\n<code>/bc سلام کاربران عزیز، نسخه جدید ربات منتشر شد!</code>", 
                    parse_mode="HTML"
                )
                return
            
            bulk_text = command_text[1].strip()
            
            from src.database.db_manager import create_broadcast_campaign
            campaign_id = await create_broadcast_campaign(bulk_text)
            
            await bot.reply_to(
                message, 
                f"{EMOJI['thunder']['html']} <b>فرمان ارسال پیام همگانی صادر شد!</b>\n\n"
                f"{EMOJI['id']['html']} کد کمپین: <code>{campaign_id}</code>\n"
                f"{EMOJI['clock']['html']} وضعیت: <i>در صف ارسال بک‌گراند سرور...</i>\n\n"
                f"ربات بدون وقفه به کارش ادامه میده و پس از اتمام ارسال، گزارش نهایی رو همین‌جا برات می‌فرسته. {EMOJI['sus']['html']}",
                parse_mode="HTML"
            )
            
        except Exception as err:
            print(f"💥 Failed to initiate broadcast campaign: {err}")
            await bot.reply_to(message, f"{EMOJI['ban']['html']} خطای فنی در ثبت کمپین پیام همگانی.", parse_mode="HTML")

    # ==========================================
    # 🎰 دستور تِست و دریافت لیست کامل اموجی‌های پرمیوم ست شده
    # ==========================================
    @bot.message_handler(commands=["emoji"], func=lambda m: m.chat.id in SUPER_USERS)
    async def send_emojis(message):
        try:
            for key, value in EMOJI.items():
                await bot.send_message(message.chat.id, f"{EMOJI['pin']['html']} <b>Key:</b> <code>{key}</code>\n{EMOJI['ball']['html']} <b>Render:</b> {value['html']}", parse_mode="HTML")
        except Exception as e:
            print(f"💥 Error printing emojis: {e}")

    # ==========================================
    # 🎨 بخش مدیریت اختصاصی و سرقت پک اموجی پرمیوم (Custom Emoji Manager)
    # ==========================================

    # 🥷 تابع کمکی فوق هوشمند برای استخراج فایل یا سرقت اموجی پرمیوم از ریپلای
    async def get_file_details(msg):
        if not msg.reply_to_message: return None, None, None
        reply = msg.reply_to_message
        
        if reply.sticker:
            fmt = "animated" if reply.sticker.is_animated else ("video" if reply.sticker.is_video else "static")
            return reply.sticker.file_id, fmt, reply.sticker.emoji

        entities = reply.entities or reply.caption_entities
        if entities:
            for ent in entities:
                if ent.type == 'custom_emoji':
                    stickers = await bot.get_custom_emoji_stickers([ent.custom_emoji_id])
                    if stickers:
                        s = stickers[0]
                        fmt = "animated" if s.is_animated else ("video" if s.is_video else "static")
                        return s.file_id, fmt, s.emoji

        doc = reply.document or reply.video
        if doc:
            file_name = getattr(doc, 'file_name', '').lower()
            if file_name.endswith('.tgs') or getattr(doc, 'is_animated', False):
                fmt = "animated"
            elif file_name.endswith('.webm') or getattr(doc, 'is_video', False):
                fmt = "video"
            else:
                fmt = "static"
            return doc.file_id, fmt, None
            
        return None, None, None

    # 🛠 تابع کمکی برای فرمت‌دهی نام پک
    async def get_full_pack_name(short_name):
        bot_info = await bot.get_me()
        bot_user = bot_info.username
        if not short_name.endswith(f"_by_{bot_user}"):
            return f"{short_name}_by_{bot_user}"
        return short_name

    # ۱. 📦 ساخت پک جدید
    @bot.message_handler(commands=['create_pack'], func=lambda m: m.chat.id in SUPER_USERS)
    async def admin_create_pack(message):
        try:
            args = message.text.split(maxsplit=3)
            if len(args) < 3:
                return await bot.reply_to(message, f"{EMOJI['caution']['html']} فرمت:\n`/create_pack pack_name Title [🎯]`\n*(اگر روی فایل ریپلای می‌کنی اموجی رو بنویس، اگر روی اموجی پرمیوم ریپلای زدی خودش می‌فهمه!)*", parse_mode="HTML")
            
            short_name, title = args[1], args[2]
            file_id, fmt, extracted_emoji = await get_file_details(message)
            
            if not file_id:
                return await bot.reply_to(message, f"{EMOJI['ban']['html']} لطفاً روی یک اموجی پرمیوم یا فایل خام ریپلای کن!", parse_mode="HTML")

            emoji = args[3] if len(args) > 3 else extracted_emoji
            if not emoji:
                return await bot.reply_to(message, f"{EMOJI['ban']['html']} نتونستم اموجی رو پیدا کنم. خودت اموجی کیبورد رو آخر دستور بنویس.", parse_mode="HTML")

            full_pack_name = await get_full_pack_name(short_name)
            sticker = InputSticker(sticker=file_id, emoji_list=[emoji])
            
            msg = await bot.reply_to(message, f"{EMOJI['clock']['html']} در حال ساخت پک اختصاصی...", parse_mode="HTML")
            
            success = await bot.create_new_sticker_set(
                user_id=GOD_ID,
                name=full_pack_name,
                title=title.replace("_", " "),
                stickers=[sticker],
                sticker_format=fmt,
                sticker_type="custom_emoji"
            )
            
            if success:
                pack = await bot.get_sticker_set(full_pack_name)
                new_id = pack.stickers[0].custom_emoji_id
                await bot.edit_message_text(
                    f"{EMOJI['crcl_yes']['html']} **پک با موفقیت ساخته شد!**\n\n"
                    f"{EMOJI['present']['html']} 📦 نام پک: <code>{full_pack_name}</code>\n"
                    f"{EMOJI['link']['html']} <a href='https://t.me/addstickers/{full_pack_name}'>لینک پک شما</a>\n\n"
                    f"{EMOJI['gem']['html']} **آیدی اموجی برای فایل کانفیگ:**\n<code>\"{new_id}\"</code>",
                    chat_id=message.chat.id, message_id=msg.message_id, parse_mode="HTML", disable_web_page_preview=True
                )
        except Exception as e:
            await bot.reply_to(message, f"{EMOJI['bang']['html']} خطا در ساخت پک:\n<code>{e}</code>", parse_mode="HTML")

    # ۲. ➕ افزودن / سرقت اموجی به پک
    @bot.message_handler(commands=['add_emoji'], func=lambda m: m.chat.id in SUPER_USERS)
    async def admin_add_emoji(message):
        try:
            args = message.text.split(maxsplit=2)
            if len(args) < 2:
                return await bot.reply_to(message, f"{EMOJI['caution']['html']} فرمت:\n`/add_emoji pack_name [🎯]`\n*(روی اموجی پرمیوم دلخواه ریپلای کن تا کپی بشه تو پکت!)*", parse_mode="HTML")
            
            pack_name = args[1]
            file_id, fmt, extracted_emoji = await get_file_details(message)
            
            if not file_id:
                return await bot.reply_to(message, f"{EMOJI['ban']['html']} لطفاً روی یک فایل یا اموجی پرمیوم ریپلای کن!", parse_mode="HTML")

            emoji = args[2] if len(args) > 2 else extracted_emoji
            if not emoji:
                return await bot.reply_to(message, f"{EMOJI['ban']['html']} نتونستم اموجی رو تشخیص بدم، لطفاً خودت اموجی کیبورد رو بعد از اسم پک بنویس.", parse_mode="HTML")

            full_pack_name = await get_full_pack_name(pack_name)
            sticker = InputSticker(sticker=file_id, emoji_list=[emoji])
            
            msg = await bot.reply_to(message, f"{EMOJI['clock']['html']} در حال افزودن/سرقت اموجی پرمیوم به پک شما...", parse_mode="HTML")
            
            success = await bot.add_sticker_to_set(
                user_id=GOD_ID,
                name=full_pack_name,
                sticker=sticker
            )
            
            if success:
                pack = await bot.get_sticker_set(full_pack_name)
                new_id = pack.stickers[-1].custom_emoji_id
                await bot.edit_message_text(
                    f"{EMOJI['crcl_yes']['html']} **اموجی با موفقیت کپی شد!**\n\n"
                    f"{EMOJI['gem']['html']} **آیدی اموجی برای فایل کانفیگ:**\n<code>\"{new_id}\"</code>",
                    chat_id=message.chat.id, message_id=msg.message_id, parse_mode="HTML"
                )
        except Exception as e:
            err_msg = str(e)
            if "STICKER_FORMAT_INVALID" in err_msg:
                await bot.reply_to(message, f"{EMOJI['red_caution']['html']} **خطای فرمت:** اموجی‌ای که کپی می‌کنی فرمتش با پکت فرق داره! (مثلاً نمیشه اموجی `.webm` ویدیویی رو تو پک `.tgs` انیمیشنی ادغام کرد)", parse_mode="HTML")
            else:
                await bot.reply_to(message, f"{EMOJI['bang']['html']} خطا در افزودن اموجی:\n<code>{e}</code>", parse_mode="HTML")

    # ۳. 📋 دریافت لیست اموجی‌های یک پک
    @bot.message_handler(commands=['list_pack'], func=lambda m: m.chat.id in SUPER_USERS)
    async def admin_list_pack(message):
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                return await bot.reply_to(message, f"{EMOJI['caution']['html']} فرمت:\n`/list_pack pack_name`", parse_mode="HTML")
            
            full_pack_name = await get_full_pack_name(args[1])
            pack = await bot.get_sticker_set(full_pack_name)
            
            res = f"{EMOJI['present']['html']} **پک:** <code>{pack.title}</code>\nتعداد اموجی‌ها: {len(pack.stickers)}\n\n"
            for i, s in enumerate(pack.stickers):
                res += f"[{i+1}] {s.emoji}\n"
                res += f"{EMOJI['gem']['html']} **Custom ID:** <code>{s.custom_emoji_id}</code>\n"
                res += f"{EMOJI['trash']['html']} **File ID:** <code>{s.file_id}</code>\n\n"
                
            for x in range(0, len(res), 4000):
                await bot.send_message(message.chat.id, res[x:x+4000], parse_mode="HTML")
                
        except Exception as e:
            await bot.reply_to(message, f"{EMOJI['bang']['html']} خطا در دریافت لیست:\n<code>{e}</code>", parse_mode="HTML")

    # ۴. 🗑 حذف یک اموجی از پک
    @bot.message_handler(commands=['del_emoji'], func=lambda m: m.chat.id in SUPER_USERS)
    async def admin_del_emoji(message):
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                return await bot.reply_to(message, f"{EMOJI['caution']['html']} فرمت:\n`/del_emoji FILE_ID`\n*(فایل آیدی رو از دستور /list_pack بگیر)*", parse_mode="HTML")
            
            file_id = args[1].strip()
            success = await bot.delete_sticker_from_set(file_id)
            
            if success:
                await bot.reply_to(message, f"{EMOJI['trash']['html']} **اموجی با موفقیت از پک حذف شد!**", parse_mode="HTML")
        except Exception as e:
            await bot.reply_to(message, f"{EMOJI['bang']['html']} خطا در حذف اموجی:\n<code>{e}</code>", parse_mode="HTML")