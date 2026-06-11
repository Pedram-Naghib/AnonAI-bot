import re
import traceback
import asyncio
from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReplyKeyboardRemove

# وارد کردن تنظیمات و توابع پایه مورد نیاز
from src.config import GROUP_CHAT_ID
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
            await bot.reply_to(message, f"🆔 آیدی این چت/گروه: `{message.chat.id}`\n", parse_mode="Markdown")
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
                await bot.reply_to(message, f"🎯 روی پیام `{reply_to_msg_id}` ریپلای شد!")
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
                # ۱. دریافت تعداد کل کاربران ثبت‌شده در دیتابیس
                total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
                # ۲. دریافت تعداد کاربران مسدود شناسایی‌شده
                total_dead_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE anon_state = 'blocked_bot'")
                
                # ۳. استخراج کاربران فعال (آن‌هایی که از قبل به عنوان بلاک شناسایی نشده‌اند)
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
                    WHERE u.anon_state != 'blocked_bot' -- فقط کاربران زنده اسکن شوند
                    ORDER BY (COALESCE(r.received_count, 0) + COALESCE(s.sent_count, 0)) DESC
                    LIMIT 30;
                """
                
                rows = await conn.fetch(query)
                if not rows:
                    await bot.reply_to(message, f"📭 هیچ کاربری یافت نشد.\n👥 کل اعضا: {total_users}")
                    return

                # 🛠️ پاتک موازی شناسایی و نشانه‌گذاری کاربران بلاک‌کننده در دیتابیس
                async def check_and_clean_user(row):
                    uid = row['user_id']
                    try:
                        await asyncio.wait_for(bot.send_chat_action(uid, 'typing'), timeout=1.5)
                        return row, True
                    except Exception:
                        # 🔥 کاربر ربات را بلاک کرده؛ بلافاصله وضعیتش را در دیتابیس ایزوله می‌کنیم
                        async with pool.acquire() as db_conn:
                            await db_conn.execute("UPDATE users SET anon_state = 'blocked_bot', chat_status = 'idle', active_partner_id = NULL WHERE user_id = $1", uid)
                        return row, False

                # اجرای هم‌زمان موازی تست وضعیت کاربران برتر
                tasks = [check_and_clean_user(row) for row in rows]
                checked_results = await asyncio.gather(*tasks)

                # محاسبه مجدد لایو اعضای فعال واقعی
                live_users_count = total_users - total_dead_users

                report_lines = [
                    "👑 <b>گزارش ارشد وضعیت دیتابیس</b>\n",
                    f"👥 کل کاربران ثبت شده: <b>{total_users}</b>",
                    f"🟢 کاربران فعال و زنده: <b>{live_users_count}</b>",
                    f"🔴 مسدودکنندگان شناسایی‌شده: <b>{total_dead_users}</b>\n",
                    "📊 <i>۲۰ کاربر برتر بر اساس بیشترین حجم تعاملات ناشناس:</i>\n"
                ]
                
                valid_count = 0
                for row, is_active in checked_results:
                    if not is_active: continue # رد کردن کاربرانی که همین الان بلاک کردند
                    
                    valid_count += 1
                    uid = row['user_id']
                    name = row['first_name'] or "Unknown"
                    username = f"@{row['username']}" if row['username'] else "بدون یوزرنیم"
                    received = row['received']
                    sent = row['sent']
                    
                    line = (
                        f"{valid_count}. 👤 <b>{name}</b> (<code>{uid}</code>) | {username}\n"
                        f"   📥 دریافتی: <b>{received}</b> | 📤 ارسالی: <b>{sent}</b>\n"
                        f"   ➖"
                    )
                    report_lines.append(line)
                    
                    if valid_count >= 20: break

                final_report = "\n".join(report_lines)
                await bot.reply_to(message, final_report, parse_mode="HTML")
                
        except Exception as err:
            print(f"💥 Admin Stats Command Failed: {err}")
            traceback.print_exc()
            await bot.reply_to(message, "❌ خطای فنی در استخراج اطلاعات از دیتابیس.")

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
                    "⚠️ <b>فرمت اشتباه است!</b>\n"
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
                f"🚀 <b>فرمان ارسال پیام همگانی صادر شد!</b>\n\n"
                f"📦 کد کمپین: <code>{campaign_id}</code>\n"
                f"📝 وضعیت: <i>در صف ارسال بک‌گراند سرور...</i>\n\n"
                f"ربات بدون وقفه به کارش ادامه میده و پس از اتمام ارسال، گزارش نهایی رو همین‌جا برات می‌فرسته. 🕶️✨",
                parse_mode="HTML"
            )
            
        except Exception as err:
            print(f"💥 Failed to initiate broadcast campaign: {err}")
            await bot.reply_to(message, "❌ خطای فنی در ثبت کمپین پیام همگانی.")

    # ==========================================
    # 🎰 دستور تِست و دریافت لیست کامل اموجی‌های پرمیوم ست شده
    # ==========================================
    # 🔥 رفع باگ دستور commands و داینامیک کردن آیدی چت فرستنده
    @bot.message_handler(commands=["emoji"], func=lambda m: m.chat.id == 8627765327)
    async def send_emojis(message):
        try:
            from src.config import EMOJI
            
            # ارسال تکی برای مشخص شدن تفکیک رندر شدن کدهای اموجی
            for key, value in EMOJI.items():
                await bot.send_message(message.chat.id, f"📌 <b>Key:</b> `{key}`\n🔮 <b>Render:</b> {value}", parse_mode="HTML")
        except Exception as e:
            print(f"💥 Error printing emojis: {e}")